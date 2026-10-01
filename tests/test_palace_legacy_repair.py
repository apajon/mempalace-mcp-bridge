"""Tests for the narrow legacy repair contract and its storage profiles.

These tests never touch a real palace: every fixture is built from a real
ChromaDB palace created inside a temporary directory (see ``palace_fixtures``).

Two **independent** legacy profiles are covered explicitly, rather than a single
undifferentiated "legacy" concept:

* ``Native0_6LegacyProfileTests`` — a native 0.6.x schema (``sysdb 9`` /
  ``metadb 4``, blob ``seq_id``) carrying an untyped ``{}`` configuration. This
  is the historical case described by the bridge documentation.
* ``Post1XLegacyProfileTests`` — a schema migrated by ChromaDB 1.x (``sysdb 10``
  / ``metadb 6``, integer ``seq_id``, ``schema_str``, ``acquire_write``,
  ``embedding_metadata_array``) carrying an untyped ``{}`` configuration. This is
  the profile observed on the reference machine.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
TESTS_DIR = REPO_ROOT / "tests"
for _directory in (SCRIPTS_DIR, TESTS_DIR):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))

import palace_fixtures as fx  # type: ignore
from palace_format_detector import (  # type: ignore
    CLASS_CHROMA_0_6,
    CLASS_CHROMA_1_X,
    CLASS_UNKNOWN,
    detect_palace_format,
)
from palace_legacy_repair import (  # type: ignore
    PROFILE_NATIVE_0_6,
    PROFILE_POST_1_X,
    PROFILE_UNKNOWN,
    create_sqlite_backup,
    detect_storage_profile,
    evaluate_legacy_repair_eligibility,
    repair_legacy_palace,
)


TYPED_CONFIG = fx.TYPED_CONFIG


def _backup_files(palace: Path) -> list[Path]:
    return sorted(palace.glob("chroma.sqlite3.bak-*"))


class _PalaceTestCase(unittest.TestCase):
    """Base class: skip cleanly when ChromaDB is unavailable, isolate each test."""

    def setUp(self) -> None:
        try:
            fx.require_chromadb()
        except Exception as exc:  # pragma: no cover - environment dependent
            self.skipTest(f"chromadb unavailable: {exc}")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.palace = self.root / "palace"

    @staticmethod
    def _provider() -> str:
        return TYPED_CONFIG

    @staticmethod
    def _probe_ok(_path: Path, _name: str) -> tuple[bool, str]:
        return True, "5 drawers"



def _write_manifest(palace: Path, payload: dict[str, object]) -> None:
    fx.write_manifest(palace, payload)


class StorageProfileDetectionTests(_PalaceTestCase):
    """`detect_storage_profile` is a provenance question, separate from gating."""

    def test_healthy_native_palace_is_native_profile(self) -> None:
        fx.build_healthy_native_palace(self.palace)

        result = detect_storage_profile(self.palace)

        self.assertEqual(result.profile, PROFILE_NATIVE_0_6)
        self.assertEqual(result.schema_versions, fx.NATIVE_0_6_MIGRATIONS)
        self.assertTrue(all(item.passed for item in result.evidence))

    def test_post_1_x_migrated_palace_is_post_1_x_profile(self) -> None:
        fx.create_typed_palace(self.palace)
        fx.apply_post_1_x_migration_steps(self.palace)

        result = detect_storage_profile(self.palace)

        self.assertEqual(result.profile, PROFILE_POST_1_X)
        self.assertEqual(result.schema_versions, fx.POST_1_X_MIGRATIONS)

    def test_half_migrated_palace_matches_no_profile(self) -> None:
        # Integer seq_id but 0.6.x migrations: a partially migrated palace.
        fx.build_healthy_native_palace(self.palace)
        fx.convert_seq_id_to_integer(self.palace)

        result = detect_storage_profile(self.palace)

        self.assertEqual(result.profile, PROFILE_UNKNOWN)
        self.assertTrue(result.failed_evidence())

    def test_missing_database_matches_no_profile(self) -> None:
        self.palace.mkdir(parents=True, exist_ok=True)

        result = detect_storage_profile(self.palace)

        self.assertEqual(result.profile, PROFILE_UNKNOWN)

    def test_post_1_x_palace_is_runtime_compatible_but_not_native(self) -> None:
        # The whole point of the separation: 0.6.3 opens it, but it is NOT a
        # 0.6.x-native schema.
        fx.create_typed_palace(self.palace)
        fx.apply_post_1_x_migration_steps(self.palace)

        self.assertEqual(detect_palace_format(self.palace).classification, CLASS_CHROMA_0_6)
        self.assertEqual(detect_storage_profile(self.palace).profile, PROFILE_POST_1_X)


class Native0_6LegacyProfileTests(_PalaceTestCase):
    """Profile A — native 0.6.x schema (sysdb 9 / metadb 4, blob seq_id) + '{}'."""

    def test_native_0_6_legacy_profile_is_a_real_failure(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)

        self.assertEqual(detect_palace_format(self.palace).classification, CLASS_UNKNOWN)
        self.assertEqual(detect_storage_profile(self.palace).profile, PROFILE_NATIVE_0_6)

        import chromadb

        with self.assertRaises(Exception):
            client = chromadb.PersistentClient(path=str(self.palace))
            client.get_or_create_collection(fx.COLLECTION_NAME)

    def test_native_0_6_legacy_profile_is_repair_eligible(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertTrue(result.eligible, msg=[item.detail for item in result.failed_invariants()])
        self.assertEqual(result.profile, PROFILE_NATIVE_0_6)
        self.assertEqual(result.schema_versions, fx.NATIVE_0_6_MIGRATIONS)

    def test_native_0_6_legacy_profile_is_repaired_and_readable(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)

        report = repair_legacy_palace(self.palace, write_manifest=False)

        self.assertEqual(report.status, "repaired", msg=report.errors)
        self.assertEqual(report.profile, PROFILE_NATIVE_0_6)
        self.assertEqual(report.detection_after, CLASS_CHROMA_0_6)

        import chromadb

        client = chromadb.PersistentClient(path=str(self.palace))
        self.assertEqual(
            client.get_or_create_collection(fx.COLLECTION_NAME).count(), fx.DRAWER_COUNT
        )

    def test_native_0_6_backup_holds_the_untyped_config(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)

        report = repair_legacy_palace(
            self.palace,
            config_provider=self._provider,
            connectivity_probe=self._probe_ok,
            write_manifest=False,
        )

        self.assertTrue(report.backup_path)
        backup = Path(report.backup_path or "")
        self.assertTrue(backup.exists())
        conn = sqlite3.connect(str(backup))
        try:
            self.assertEqual(
                conn.execute("SELECT config_json_str FROM collections").fetchone()[0], "{}"
            )
        finally:
            conn.close()
        self.assertEqual(fx.read_config_value(self.palace), TYPED_CONFIG)

    def test_null_config_is_runtime_compatible_and_not_repairable(self) -> None:
        # A NULL config is opened fine by 0.6.x, so it must never be mutated.
        fx.build_healthy_native_palace(self.palace)
        fx.set_config_value(self.palace, None)

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)
        self.assertIn("no_null_config", [item.name for item in result.failed_invariants()])

    def test_empty_string_config_is_not_repairable(self) -> None:
        fx.build_healthy_native_palace(self.palace)
        fx.set_config_value(self.palace, "")

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)
        self.assertIn("no_empty_string_config", [item.name for item in result.failed_invariants()])

    def test_native_profile_with_post_1_x_tables_is_rejected(self) -> None:
        # 0.6.x migrations but 1.x tables: a hybrid that matches no profile.
        fx.build_native_0_6_legacy_palace(self.palace)
        fx.add_foreign_table(self.palace, "acquire_write")

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)
        self.assertIn("storage_profile_known", [item.name for item in result.failed_invariants()])

    def test_native_profile_with_integer_seq_id_is_rejected(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)
        fx.convert_seq_id_to_integer(self.palace)

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)

    def test_native_profile_with_post_1_x_migrations_is_rejected(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)
        fx.set_migrations(self.palace, fx.POST_1_X_MIGRATIONS)

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)
        self.assertIn("storage_profile_known", [item.name for item in result.failed_invariants()])


class Post1XLegacyProfileTests(_PalaceTestCase):
    """Profile B — 1.x-migrated schema (sysdb 10 / metadb 6) + '{}'."""

    def test_post_1_x_legacy_profile_is_repair_eligible(self) -> None:
        fx.build_post_1_x_legacy_palace(self.palace)

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertTrue(result.eligible, msg=[item.detail for item in result.failed_invariants()])
        self.assertEqual(result.profile, PROFILE_POST_1_X)
        self.assertEqual(result.schema_versions, fx.POST_1_X_MIGRATIONS)

    def test_post_1_x_legacy_profile_is_repaired_and_readable(self) -> None:
        fx.build_post_1_x_legacy_palace(self.palace)

        self.assertEqual(detect_palace_format(self.palace).classification, CLASS_UNKNOWN)

        report = repair_legacy_palace(self.palace, write_manifest=False)

        self.assertEqual(report.status, "repaired", msg=report.errors)
        self.assertEqual(report.profile, PROFILE_POST_1_X)
        self.assertEqual(report.detection_after, CLASS_CHROMA_0_6)
        self.assertTrue(report.backup_path and Path(report.backup_path).exists())

        import chromadb

        client = chromadb.PersistentClient(path=str(self.palace))
        self.assertEqual(
            client.get_or_create_collection(fx.COLLECTION_NAME).count(), fx.DRAWER_COUNT
        )

    def test_post_1_x_profile_without_1_x_tables_is_rejected(self) -> None:
        fx.build_post_1_x_legacy_palace(self.palace)
        fx.drop_table(self.palace, "acquire_write")

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)
        self.assertIn("storage_profile_known", [item.name for item in result.failed_invariants()])

    def test_post_1_x_profile_with_blob_seq_id_is_rejected(self) -> None:
        # 1.x tables/columns but 0.6.x blob seq_id: half-migrated, must be refused.
        fx.create_typed_palace(self.palace)
        fx.apply_post_1_x_migration_steps(self.palace)
        fx.set_config_value(self.palace, "{}")
        conn = sqlite3.connect(str(self.palace / "chroma.sqlite3"))
        conn.execute("UPDATE embeddings SET seq_id = zeroblob(8)")
        conn.commit()
        conn.close()

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)

    def test_post_1_x_profile_missing_bool_value_is_rejected(self) -> None:
        fx.build_post_1_x_legacy_palace(self.palace)
        # Rebuild embedding_metadata without the bool_value column.
        conn = sqlite3.connect(str(self.palace / "chroma.sqlite3"))
        conn.execute(
            "CREATE TABLE embedding_metadata_nb (id INTEGER, key TEXT NOT NULL, "
            "string_value TEXT, int_value INTEGER, float_value REAL)"
        )
        conn.execute("DROP TABLE embedding_metadata")
        conn.execute("ALTER TABLE embedding_metadata_nb RENAME TO embedding_metadata")
        conn.commit()
        conn.close()

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)


class ProfileIndependentRejectionTests(_PalaceTestCase):
    """Cases that must be refused whatever the storage profile is."""

    def test_healthy_typed_palace_is_not_repair_eligible(self) -> None:
        fx.build_healthy_native_palace(self.palace)

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)
        self.assertEqual(detect_palace_format(self.palace).classification, CLASS_CHROMA_0_6)

    def test_typed_post_1_x_palace_is_not_repair_eligible(self) -> None:
        fx.create_typed_palace(self.palace)
        fx.apply_post_1_x_migration_steps(self.palace)

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)

    def test_explicit_1_x_palace_is_not_repair_eligible(self) -> None:
        fx.build_post_1_x_legacy_palace(self.palace)
        fx.write_manifest(
            self.palace,
            {"compatibility_line": "chromadb-1.x", "chromadb_version": "1.5.7"},
        )

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertEqual(detect_palace_format(self.palace).classification, CLASS_CHROMA_1_X)
        self.assertFalse(result.eligible)

    def test_unknown_arbitrary_palace_is_not_repair_eligible(self) -> None:
        self.palace.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.palace / "chroma.sqlite3"))
        conn.execute(
            "CREATE TABLE collections (id TEXT, name TEXT, config_json_str TEXT)"
        )
        conn.execute("INSERT INTO collections VALUES ('x', ?, '{}')", (fx.COLLECTION_NAME,))
        conn.commit()
        conn.close()

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)
        self.assertIn("storage_profile_known", [item.name for item in result.failed_invariants()])

    def test_missing_database_is_not_repair_eligible(self) -> None:
        self.palace.mkdir(parents=True, exist_ok=True)

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)

    def test_non_empty_untyped_config_is_not_repair_eligible(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)
        fx.set_config_value(self.palace, json.dumps({"foo": 1}))

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)
        self.assertIn("no_unexpected_config", [item.name for item in result.failed_invariants()])

    def test_invalid_json_config_is_not_repair_eligible(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)
        fx.set_config_value(self.palace, "{not json")

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)

    def test_mixed_configs_are_not_repair_eligible(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)
        fx.add_extra_collection(self.palace, "other", TYPED_CONFIG)

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)
        self.assertIn("all_configs_untyped", [item.name for item in result.failed_invariants()])

    def test_missing_expected_collection_is_not_repair_eligible(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace, collection_name="something_else")

        result = evaluate_legacy_repair_eligibility(
            self.palace, expected_collection="mempalace_drawers"
        )

        self.assertFalse(result.eligible)
        self.assertIn("expected_collection", [item.name for item in result.failed_invariants()])

    def test_contradictory_manifest_blocks_repair(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)
        _write_manifest(
            self.palace, {"compatibility_line": "custom-line", "chromadb_version": "9.9.9"}
        )

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)
        self.assertIn("manifest_not_contradictory", [item.name for item in result.failed_invariants()])

    def test_unreadable_manifest_blocks_repair(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)
        fx.write_manifest_text(self.palace, "{not json")

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)

    def test_manifest_declaring_1_x_storage_profile_blocks_repair(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)
        _write_manifest(
            self.palace,
            {
                "compatibility_line": "chromadb-0.6.x",
                "chromadb_version": "0.6.3",
                "storage_profile": "chroma_1_x_migrated",
            },
        )

        # The declared provenance contradicts the detected native schema.
        result = detect_storage_profile(self.palace)
        self.assertEqual(result.profile, PROFILE_NATIVE_0_6)

    def test_integrity_failure_is_not_repair_eligible(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)
        fx.corrupt_database(self.palace)

        result = evaluate_legacy_repair_eligibility(self.palace)

        self.assertFalse(result.eligible)
        self.assertTrue(
            {"sqlite_openable", "sqlite_integrity", "storage_profile_known"}
            & {item.name for item in result.failed_invariants()}
        )


class LegacyRepairApplyTests(_PalaceTestCase):
    """Repair mechanics: backup, transaction, rollback, restore."""

    def test_repair_reports_success_and_the_detected_profile(self) -> None:
        fx.build_post_1_x_legacy_palace(self.palace)

        report = repair_legacy_palace(
            self.palace,
            config_provider=self._provider,
            connectivity_probe=self._probe_ok,
            write_manifest=False,
        )

        self.assertEqual(report.status, "repaired")
        self.assertEqual(report.detection_before, CLASS_UNKNOWN)
        self.assertEqual(report.detection_after, CLASS_CHROMA_0_6)
        self.assertEqual(report.profile, PROFILE_POST_1_X)
        self.assertEqual(fx.read_config_value(self.palace), TYPED_CONFIG)
        self.assertEqual(detect_palace_format(self.palace).classification, CLASS_CHROMA_0_6)

    def test_backup_is_never_overwritten(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)
        db_path = self.palace / "chroma.sqlite3"
        stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)

        first = create_sqlite_backup(db_path, stamp)
        second = create_sqlite_backup(db_path, stamp)

        self.assertNotEqual(first, second)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

    def test_backup_restored_when_post_repair_validation_fails(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)

        report = repair_legacy_palace(
            self.palace,
            config_provider=self._provider,
            connectivity_probe=lambda _path, _name: (False, "boom"),
            write_manifest=False,
        )

        self.assertEqual(report.status, "restored")
        self.assertEqual(fx.read_config_value(self.palace), "{}")
        self.assertEqual(detect_palace_format(self.palace).classification, CLASS_UNKNOWN)

    def test_provider_failure_leaves_palace_untouched(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)

        def raising_provider() -> str:
            raise RuntimeError("provider failure")

        report = repair_legacy_palace(
            self.palace,
            config_provider=raising_provider,
            connectivity_probe=self._probe_ok,
            write_manifest=False,
        )

        self.assertEqual(report.status, "failed")
        self.assertEqual(fx.read_config_value(self.palace), "{}")
        self.assertEqual(_backup_files(self.palace), [])

    def test_ineligible_palace_is_never_mutated(self) -> None:
        # A hybrid (0.6.x migrations + a 1.x table) matches no profile.
        fx.build_native_0_6_legacy_palace(self.palace)
        fx.add_foreign_table(self.palace, "acquire_write")

        report = repair_legacy_palace(
            self.palace,
            config_provider=self._provider,
            connectivity_probe=self._probe_ok,
            write_manifest=False,
        )

        self.assertEqual(report.status, "ineligible")
        self.assertEqual(fx.read_config_value(self.palace), "{}")
        self.assertEqual(_backup_files(self.palace), [])


class ManifestProvenanceTests(unittest.TestCase):
    """The manifest must record provenance, not only the runtime version."""

    def _manifest(self, **kwargs):
        from palace_manifest import build_manifest

        return build_manifest(REPO_ROOT, **kwargs)

    def test_manifest_records_explicit_provenance(self) -> None:
        from palace_manifest import validate_manifest

        manifest = self._manifest(
            storage_profile=PROFILE_POST_1_X, schema_versions=fx.POST_1_X_MIGRATIONS
        )

        self.assertEqual(manifest["compatibility_line"], "chromadb-0.6.x")
        self.assertEqual(manifest["storage_profile"], PROFILE_POST_1_X)
        self.assertEqual(manifest["storage_schema_versions"], fx.POST_1_X_MIGRATIONS)
        self.assertIsNone(validate_manifest(manifest))

    def test_validate_manifest_rejects_malformed_provenance(self) -> None:
        from palace_manifest import validate_manifest

        manifest = self._manifest(storage_profile=PROFILE_NATIVE_0_6, schema_versions={})
        manifest["storage_schema_versions"] = {"sysdb": "not-an-int"}
        self.assertIsNotNone(validate_manifest(manifest))

    def test_validate_manifest_rejects_empty_profile_string(self) -> None:
        from palace_manifest import validate_manifest

        manifest = self._manifest(storage_profile=PROFILE_NATIVE_0_6, schema_versions={})
        manifest["storage_profile"] = "  "
        self.assertIsNotNone(validate_manifest(manifest))

    def test_validate_manifest_still_accepts_legacy_manifests(self) -> None:
        from palace_manifest import validate_manifest

        manifest = self._manifest(storage_profile=PROFILE_NATIVE_0_6, schema_versions={})
        manifest.pop("storage_profile")
        manifest.pop("storage_schema_versions")
        self.assertIsNone(validate_manifest(manifest))


if __name__ == "__main__":
    unittest.main()
