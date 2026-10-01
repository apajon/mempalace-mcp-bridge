from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
TESTS_DIR = REPO_ROOT / "tests"
for _directory in (SCRIPTS_DIR, TESTS_DIR):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))

import palace_fixtures as fx  # type: ignore
from palace_format_detector import MANIFEST_FILENAME  # type: ignore
from palace_safety_gate import evaluate_palace_safety  # type: ignore


class _ProfilePalaceTestCase(unittest.TestCase):
    """Base class for tests that need a real ChromaDB palace fixture."""

    def setUp(self) -> None:
        try:
            fx.require_chromadb()
        except Exception as exc:  # pragma: no cover - environment dependent
            self.skipTest(f"chromadb unavailable: {exc}")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.palace = Path(self.temp_dir.name) / "palace"


class PalaceSafetyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_manifest(self, palace: Path, payload: dict[str, object]) -> None:
        palace.mkdir(parents=True, exist_ok=True)
        (palace / MANIFEST_FILENAME).write_text(json.dumps(payload), encoding="utf-8")

    def _write_sqlite(self, palace: Path, config_values: list[str]) -> None:
        palace.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(palace / "chroma.sqlite3")
        cur = conn.cursor()
        cur.execute("CREATE TABLE collections (config_json_str TEXT)")
        cur.executemany(
            "INSERT INTO collections (config_json_str) VALUES (?)",
            [(value,) for value in config_values],
        )
        conn.commit()
        conn.close()

    def test_supported_0_6_palace_is_allowed(self) -> None:
        palace = self.root / "palace"
        self._write_manifest(
            palace,
            {"compatibility_line": "chromadb-0.6.x", "chromadb_version": "0.6.3"},
        )
        self._write_sqlite(
            palace,
            [json.dumps({"_type": "CollectionConfigurationInternal"})],
        )

        result = evaluate_palace_safety(palace, "read")

        self.assertTrue(result.allowed)
        self.assertEqual(result.classification, "chroma_0_6")

    def test_explicit_1_x_palace_is_blocked(self) -> None:
        palace = self.root / "palace"
        self._write_manifest(
            palace,
            {"compatibility_line": "chromadb-1.x", "chromadb_version": "1.5.7"},
        )
        self._write_sqlite(palace, ["{}"])

        result = evaluate_palace_safety(palace, "write")

        self.assertFalse(result.allowed)
        self.assertEqual(result.classification, "chroma_1_x")
        self.assertIn("stable bridge only opens chroma_0_6", result.message)

    def test_unknown_existing_palace_is_blocked(self) -> None:
        palace = self.root / "palace"
        self._write_sqlite(palace, ["{}"])

        result = evaluate_palace_safety(palace, "repair")

        self.assertFalse(result.allowed)
        self.assertEqual(result.classification, "unknown")
        self.assertIn("Refusing to repair", result.message)

    def test_unknown_palace_is_blocked_for_read_and_write(self) -> None:
        palace = self.root / "palace"
        self._write_sqlite(palace, ["{}"])

        for action in ("read", "write"):
            result = evaluate_palace_safety(palace, action)  # type: ignore[arg-type]
            self.assertFalse(result.allowed, msg=action)

    # The legacy-profile gate behaviour lives in LegacyProfileGateTests below,
    # which needs real ChromaDB fixtures for each storage profile.

    def test_ineligible_palace_repair_message_points_to_dedicated_command(self) -> None:
        palace = self.root / "palace"
        self._write_sqlite(palace, ["{}"])

        result = evaluate_palace_safety(palace, "repair")

        self.assertFalse(result.allowed)
        self.assertIn("palace_legacy_repair.py", result.message)
        self.assertIn("narrow legacy repair contract", result.message)

    def test_missing_palace_database_is_allowed(self) -> None:
        palace = self.root / "palace"
        palace.mkdir(parents=True, exist_ok=True)

        result = evaluate_palace_safety(palace, "create")

        self.assertTrue(result.allowed)
        self.assertEqual(result.classification, "unknown")
        self.assertIn("No existing palace database detected", result.message)


class LegacyProfileGateTests(_ProfilePalaceTestCase):
    """`repair` is authorised per known legacy profile; read/write stay blocked."""

    def test_native_0_6_profile_repair_is_allowed(self) -> None:
        fx.build_native_0_6_legacy_palace(self.palace)

        result = evaluate_palace_safety(self.palace, "repair")

        self.assertTrue(result.allowed, msg=result.message)
        self.assertEqual(result.classification, "unknown")
        self.assertIn("narrow legacy repair", result.message)

    def test_post_1_x_profile_repair_is_allowed(self) -> None:
        fx.build_post_1_x_legacy_palace(self.palace)

        result = evaluate_palace_safety(self.palace, "repair")

        self.assertTrue(result.allowed, msg=result.message)
        self.assertIn("narrow legacy repair", result.message)

    def test_legacy_profiles_still_block_read_and_write(self) -> None:
        for builder in (fx.build_native_0_6_legacy_palace, fx.build_post_1_x_legacy_palace):
            with self.subTest(builder=builder.__name__):
                palace = Path(self.temp_dir.name) / builder.__name__
                builder(palace)
                for action in ("read", "write"):
                    result = evaluate_palace_safety(palace, action)  # type: ignore[arg-type]
                    self.assertFalse(result.allowed, msg=f"{builder.__name__}:{action}")
                    self.assertIn("palace_legacy_repair.py", result.message)

    def test_null_config_profile_is_blocked_for_repair(self) -> None:
        # A NULL config is opened by the runtime, so it must not be repaired.
        fx.build_healthy_native_palace(self.palace)
        fx.set_config_value(self.palace, None)

        result = evaluate_palace_safety(self.palace, "repair")

        self.assertFalse(result.allowed)
        self.assertIn("narrow legacy repair contract", result.message)

    def test_hybrid_palace_repair_is_blocked(self) -> None:
        # 0.6.x migrations but a 1.x table: matches no profile.
        fx.build_native_0_6_legacy_palace(self.palace)
        fx.add_foreign_table(self.palace, "acquire_write")

        result = evaluate_palace_safety(self.palace, "repair")

        self.assertFalse(result.allowed)
        self.assertIn("does not match the narrow legacy repair contract", result.message)


if __name__ == "__main__":
    unittest.main()
