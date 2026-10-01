#!/usr/bin/env python3
"""Narrow, fail-closed repair of legacy ChromaDB palaces.

Background
----------
ChromaDB >= 0.6.0 stores a typed collection configuration in
``collections.config_json_str`` (``_type = "CollectionConfigurationInternal"``).
Palaces created by older releases store the untyped object ``{}`` instead and
fail to open with "No palace found".

The format detector (``palace_format_detector.py``) deliberately classifies such
palaces as ``unknown``: an untyped ``config_json_str`` alone cannot prove the
storage line. That conservatism is correct, but it must not prevent a *dedicated*
legacy repair from running.

This module keeps the two notions separate:

* **format detection** — used to decide whether the stable bridge may read/write;
* **narrow legacy repair eligibility** — a much stricter preflight that only
  authorises rewriting ``{}`` into a typed 0.6.x configuration.

Nothing here mutates a palace unless the caller explicitly requests it via
``repair_legacy_palace``, and even then only after every invariant passed and a
fresh SQLite backup was created next to the database (existing backups are never
overwritten).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from palace_format_detector import (
    CHROMA_SQLITE_FILENAME,
    CLASS_CHROMA_0_6,
    CLASS_CHROMA_1_X,
    MANIFEST_FILENAME,
    detect_palace_format,
)


# The only untyped configuration this module is allowed to rewrite. `NULL` is
# deliberately NOT included: ChromaDB 0.6.x opens a NULL config fine (verified),
# so such a palace needs no mutation at all.
LEGACY_UNTYPED_CONFIG = "{}"

# ── Storage profiles ──────────────────────────────────────────────────────────
# A storage profile describes what actually WROTE the SQLite schema. It is a
# different notion from `palace_format_detector` classification (runtime
# compatibility) and from repair eligibility.
PROFILE_NATIVE_0_6 = "chroma_0_6_native"
PROFILE_POST_1_X = "chroma_1_x_migrated"
PROFILE_UNKNOWN = "unknown"

PROFILE_LABELS = {
    PROFILE_NATIVE_0_6: "native ChromaDB 0.6.x schema",
    PROFILE_POST_1_X: "schema migrated by ChromaDB 1.x",
    PROFILE_UNKNOWN: "unknown schema generation",
}
PROFILE_CHOICES = (PROFILE_NATIVE_0_6, PROFILE_POST_1_X, PROFILE_UNKNOWN)

# Tables present in every supported profile (the 0.6.3 baseline).
CORE_TABLES = frozenset(
    {
        "collection_metadata",
        "collections",
        "databases",
        "embedding_metadata",
        "embeddings",
        "embeddings_queue",
        "embeddings_queue_config",
        "maintenance_log",
        "max_seq_id",
        "migrations",
        "segment_metadata",
        "segments",
        "tenants",
    }
)
# Tables/columns introduced by the 1.x-era migrations (absent from 0.6.3).
POST_1_X_TABLES = frozenset({"acquire_write", "embedding_metadata_array"})
NATIVE_0_6_COLLECTION_COLUMNS = frozenset(
    {"id", "name", "dimension", "database_id", "config_json_str"}
)
POST_1_X_COLLECTION_COLUMNS = NATIVE_0_6_COLLECTION_COLUMNS | {"schema_str"}

# Per-profile structural contract. Each profile is matched exactly; a palace
# that matches none (including a half-migrated one) is `unknown`.
PROFILE_SCHEMA: dict[str, dict[str, Any]] = {
    PROFILE_NATIVE_0_6: {
        "migrations": {"sysdb": 9, "metadb": 4, "embeddings_queue": 2},
        "seq_id_storage": "blob",
        "collection_columns": NATIVE_0_6_COLLECTION_COLUMNS,
        "present_tables": frozenset(),
        "absent_tables": POST_1_X_TABLES,
    },
    PROFILE_POST_1_X: {
        "migrations": {"sysdb": 10, "metadb": 6, "embeddings_queue": 2},
        "seq_id_storage": "integer",
        "collection_columns": POST_1_X_COLLECTION_COLUMNS,
        "present_tables": POST_1_X_TABLES,
        "absent_tables": frozenset(),
    },
}
# Retro-compatibility alias: the table set of the newer profile, which the
# original (over-fitted) implementation required unconditionally.
REQUIRED_TABLES = tuple(sorted(CORE_TABLES | POST_1_X_TABLES))

SEQ_ID_TABLES = ("embeddings", "max_seq_id")
DEFAULT_COLLECTION_NAME = "mempalace_drawers"

_OTHER_LINE_TOKENS = ("chromadb-1", "chromadb_1", "chromadb-1.x")

BackupFactory = Callable[[Path], Path]
ConfigProvider = Callable[[], str]
ConnectivityProbe = Callable[[Path, str], "tuple[bool | None, str]"]


@dataclass(frozen=True)
class Invariant:
    name: str
    passed: bool
    detail: str


# Backwards-compatible alias (the type is used for profile evidence too).
RepairInvariant = Invariant


@dataclass(frozen=True)
class StorageProfileResult:
    palace_path: str
    profile: str
    confidence: str
    schema_versions: dict[str, int]
    evidence: list[Invariant]

    def failed_evidence(self) -> list[Invariant]:
        return [item for item in self.evidence if not item.passed]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "palace_path": self.palace_path,
            "profile": self.profile,
            "profile_label": PROFILE_LABELS.get(self.profile, self.profile),
            "confidence": self.confidence,
            "schema_versions": self.schema_versions,
            "evidence": [asdict(item) for item in self.evidence],
        }


@dataclass(frozen=True)
class LegacyRepairEligibility:
    palace_path: str
    eligible: bool
    collection_names: list[str]
    invariants: list[Invariant]
    message: str
    profile: str = PROFILE_UNKNOWN
    schema_versions: dict[str, int] = field(default_factory=dict)

    def failed_invariants(self) -> list[Invariant]:
        return [item for item in self.invariants if not item.passed]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "palace_path": self.palace_path,
            "eligible": self.eligible,
            "profile": self.profile,
            "profile_label": PROFILE_LABELS.get(self.profile, self.profile),
            "schema_versions": self.schema_versions,
            "collection_names": self.collection_names,
            "invariants": [asdict(item) for item in self.invariants],
            "message": self.message,
        }


@dataclass
class LegacyRepairReport:
    palace_path: str
    status: str  # ineligible | repaired | failed | restored
    message: str
    backup_path: str | None = None
    updated_collections: list[str] = field(default_factory=list)
    detection_before: str = ""
    detection_after: str = ""
    profile: str = PROFILE_UNKNOWN
    schema_versions: dict[str, int] = field(default_factory=dict)
    manifest_written: bool = False
    errors: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


def _default_palace_path() -> str:
    env_path = os.environ.get("MEMPALACE_PALACE_PATH") or os.environ.get("MEMPAL_PALACE_PATH")
    if env_path:
        return env_path
    try:
        from mempalace.config import MempalaceConfig

        configured = getattr(MempalaceConfig(), "palace_path", "")
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
    except Exception:
        pass
    return "~/.mempalace/palace"


def _default_collection_name() -> str:
    try:
        from mempalace.config import MempalaceConfig

        name = getattr(MempalaceConfig(), "collection_name", "")
        if isinstance(name, str) and name.strip():
            return name.strip()
    except Exception:
        pass
    return DEFAULT_COLLECTION_NAME


def default_config_provider() -> str:
    """Return the canonical typed configuration string for the stable line."""
    from chromadb.api.configuration import CollectionConfigurationInternal

    return CollectionConfigurationInternal().to_json_str()


def _readonly_uri(db_path: Path) -> str:
    """Build a read-only SQLite URI, percent-encoding the path safely."""
    return f"{db_path.resolve().as_uri()}?mode=ro"


def _open_readonly(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(_readonly_uri(db_path), uri=True)


def _table_columns(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    columns: dict[str, str] = {}
    for row in conn.execute(f"PRAGMA table_info({table})"):
        columns[str(row[1])] = str(row[2]).upper()
    return columns


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _profile_checks(
    spec: dict[str, Any],
    tables: set[str],
    collection_columns: set[str],
    schema_versions: dict[str, int],
    metadata_columns: set[str],
    max_seq_columns: set[str],
    seq_samples: dict[str, list[str]],
) -> list[tuple[str, bool, str]]:
    """Structural checks for one storage profile. Pure function, no I/O."""
    expected_storage = str(spec["seq_id_storage"])
    expected_columns = set(spec["collection_columns"])

    seq_ok = True
    seq_detail: list[str] = []
    for table in SEQ_ID_TABLES:
        samples = seq_samples.get(table, [])
        if not samples:
            seq_ok = False
            seq_detail.append(f"{table}.seq_id has no rows to confirm the storage type")
        elif samples != [expected_storage]:
            seq_ok = False
            seq_detail.append(f"{table}.seq_id stores {samples} (expected {expected_storage})")
        else:
            seq_detail.append(f"{table}.seq_id stores {expected_storage}")

    missing_core = sorted(CORE_TABLES - tables)
    missing_extra = sorted(set(spec["present_tables"]) - tables)
    unexpected = sorted(set(spec["absent_tables"]) & tables)

    return [
        (
            "migrations",
            schema_versions == spec["migrations"],
            f"migrations={schema_versions} (expected {spec['migrations']})",
        ),
        (
            "core_tables",
            not missing_core,
            "core tables present" if not missing_core else f"missing core tables: {missing_core}",
        ),
        (
            "extra_tables",
            not missing_extra,
            "profile tables present"
            if not missing_extra
            else f"missing profile tables: {missing_extra}",
        ),
        (
            "no_foreign_tables",
            not unexpected,
            "no foreign-generation tables"
            if not unexpected
            else f"unexpected tables from another generation: {unexpected}",
        ),
        (
            "collection_columns",
            collection_columns == expected_columns,
            f"collections columns={sorted(collection_columns)} (expected {sorted(expected_columns)})",
        ),
        (
            "seq_id_storage",
            seq_ok,
            "; ".join(seq_detail),
        ),
        (
            "no_int_seq_id_leftover",
            "int_seq_id" not in max_seq_columns,
            "no leftover int_seq_id column"
            if "int_seq_id" not in max_seq_columns
            else "max_seq_id still exposes the migrated int_seq_id column",
        ),
        (
            "bool_value",
            "bool_value" in metadata_columns,
            "embedding_metadata.bool_value present"
            if "bool_value" in metadata_columns
            else "embedding_metadata is missing the bool_value column",
        ),
    ]


def detect_storage_profile(palace_path: str | Path) -> StorageProfileResult:
    """Identify which schema generation wrote a palace, structurally.

    This answers a *provenance* question and is deliberately kept separate from:

    * ``palace_format_detector`` — answers "may the stable runtime open this?"
      (runtime compatibility);
    * ``evaluate_legacy_repair_eligibility`` — answers "may this untyped palace be
      repaired?" (needs a known profile *and* an untyped config *and* integrity).

    Read-only and fail-closed: a palace matching no profile is reported as
    ``unknown``.
    """
    path = Path(palace_path).expanduser().resolve()
    db_path = path / CHROMA_SQLITE_FILENAME
    evidence: list[Invariant] = []
    schema_versions: dict[str, int] = {}

    if not db_path.is_file():
        evidence.append(Invariant("sqlite_present", False, f"{CHROMA_SQLITE_FILENAME} is missing"))
        return StorageProfileResult(str(path), PROFILE_UNKNOWN, "low", {}, evidence)

    try:
        conn = _open_readonly(db_path)
    except sqlite3.Error as exc:
        evidence.append(Invariant("sqlite_openable", False, f"could not open read-only: {exc}"))
        return StorageProfileResult(str(path), PROFILE_UNKNOWN, "low", {}, evidence)

    try:
        tables = _table_names(conn)
        collection_columns = set(_table_columns(conn, "collections"))
        for directory, version in conn.execute("SELECT dir, MAX(version) FROM migrations GROUP BY dir"):
            schema_versions[str(directory)] = int(version)

        metadata_columns = set(_table_columns(conn, "embedding_metadata")) if "embedding_metadata" in tables else set()
        max_seq_columns = set(_table_columns(conn, "max_seq_id")) if "max_seq_id" in tables else set()
        seq_samples: dict[str, list[str]] = {}
        for table in SEQ_ID_TABLES:
            if table in tables:
                seq_samples[table] = sorted(
                    {str(row[0]) for row in conn.execute(f"SELECT DISTINCT typeof(seq_id) FROM {table}")}
                )
            else:
                seq_samples[table] = []
    except sqlite3.Error as exc:
        evidence.append(Invariant("sqlite_readable", False, f"SQLite read failed: {exc}"))
        return StorageProfileResult(str(path), PROFILE_UNKNOWN, "low", schema_versions, evidence)
    finally:
        conn.close()

    matches: list[str] = []
    profile_evidence: list[Invariant] = []
    reasons: list[str] = []

    for profile, spec in PROFILE_SCHEMA.items():
        checks = _profile_checks(
            spec, tables, collection_columns, schema_versions, metadata_columns, max_seq_columns, seq_samples
        )
        failed = [(name, detail) for name, ok, detail in checks if not ok]
        if not failed:
            matches.append(profile)
            profile_evidence = [Invariant(f"profile.{name}", True, detail) for name, _ok, detail in checks]
        else:
            reasons.append(
                f"{PROFILE_LABELS[profile]}: " + "; ".join(f"{name} -> {detail}" for name, detail in failed)
            )

    if len(matches) == 1:
        return StorageProfileResult(str(path), matches[0], "high", schema_versions, profile_evidence)

    if not matches:
        evidence.append(
            Invariant(
                "storage_profile",
                False,
                "no supported legacy profile matched. " + " | ".join(reasons),
            )
        )
    else:  # pragma: no cover - profiles are structurally disjoint
        evidence.append(
            Invariant("storage_profile", False, f"ambiguous profile match: {matches}")
        )
    return StorageProfileResult(str(path), PROFILE_UNKNOWN, "low", schema_versions, evidence)


def evaluate_legacy_repair_eligibility(
    palace_path: str | Path,
    *,
    expected_collection: str | None = None,
) -> LegacyRepairEligibility:
    """Strict, read-only preflight for the narrow ``{}`` -> typed repair.

    Fail-closed: any invariant that cannot be positively confirmed is reported as
    failed, and the palace is not eligible. Eligibility requires a *known* storage
    profile; an untyped ``{}`` configuration alone is never sufficient.
    """
    path = Path(palace_path).expanduser().resolve()
    expected = expected_collection if expected_collection else _default_collection_name()
    invariants: list[Invariant] = []
    collection_names: list[str] = []

    def record(name: str, passed: bool, detail: str) -> None:
        invariants.append(Invariant(name=name, passed=passed, detail=detail))

    def ineligible(
        message: str,
        profile: str = PROFILE_UNKNOWN,
        schema_versions: dict[str, int] | None = None,
    ) -> LegacyRepairEligibility:
        return LegacyRepairEligibility(
            palace_path=str(path),
            eligible=False,
            collection_names=collection_names,
            invariants=invariants,
            message=message,
            profile=profile,
            schema_versions=dict(schema_versions or {}),
        )

    detection = detect_palace_format(path)
    record(
        "detection_not_other_line",
        detection.classification != CLASS_CHROMA_1_X,
        f"runtime detection is {detection.classification}",
    )
    if detection.classification == CLASS_CHROMA_1_X:
        return ineligible(
            "Palace explicitly belongs to another storage line; refusing the narrow legacy repair."
        )

    db_path = path / CHROMA_SQLITE_FILENAME
    if not db_path.is_file():
        record("sqlite_present", False, f"{CHROMA_SQLITE_FILENAME} is missing")
        return ineligible("No palace database found; nothing to repair.")
    record("sqlite_present", True, f"{CHROMA_SQLITE_FILENAME} present")

    # ── Manifest must not contradict the stable line ──────────────────────────
    manifest_path = path / MANIFEST_FILENAME
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            record("manifest_not_contradictory", False, f"manifest is not readable JSON: {exc}")
            return ineligible("An unreadable bridge manifest blocks the narrow legacy repair.")

        if not isinstance(manifest, dict):
            record("manifest_not_contradictory", False, "manifest root is not a JSON object")
            return ineligible("A malformed bridge manifest blocks the narrow legacy repair.")

        line = str(manifest.get("compatibility_line", "")).strip().lower()
        version = str(manifest.get("chromadb_version", "")).strip().lower()
        declares_other = line.startswith(_OTHER_LINE_TOKENS) or version.startswith("1.")
        if declares_other:
            record(
                "manifest_not_contradictory",
                False,
                f"manifest declares compatibility_line={line!r}, chromadb_version={version!r}",
            )
            return ineligible("A manifest declaring another storage line blocks the narrow legacy repair.")

        # `compatibility_line` is a *runtime* claim. `storage_profile`, when
        # present, is the provenance claim, and must stay consistent with what we
        # detect below.
        declared_profile = str(manifest.get("storage_profile", "")).strip()
        declares_stable = line == "chromadb-0.6.x" or version.startswith("0.6")
        record(
            "manifest_not_contradictory",
            declares_stable,
            f"manifest declares compatibility_line={line!r}, storage_profile={declared_profile or '<absent>'!r}",
        )
        if not declares_stable:
            return ineligible(
                "A bridge manifest that does not confirm the stable 0.6.x compatibility line blocks the repair."
            )
    else:
        record("manifest_not_contradictory", True, "no bridge manifest present")

    try:
        conn = _open_readonly(db_path)
    except sqlite3.Error as exc:
        record("sqlite_openable", False, f"could not open SQLite read-only: {exc}")
        return ineligible("The palace database could not be opened read-only.")

    rows: list[tuple[Any, ...]] = []
    try:
        record("sqlite_openable", True, "SQLite opened read-only")

        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.Error as exc:
            record("sqlite_integrity", False, f"PRAGMA integrity_check failed: {exc}")
            return ineligible("SQLite integrity check could not be performed; refusing to touch the palace.")

        integrity_ok = bool(integrity) and str(integrity[0]).lower() == "ok"
        record("sqlite_integrity", integrity_ok, f"PRAGMA integrity_check -> {integrity[0] if integrity else 'no result'}")
        if not integrity_ok:
            return ineligible("SQLite integrity check failed; refusing to touch a damaged palace.")

        try:
            rows = list(conn.execute("SELECT id, name, config_json_str FROM collections"))
        except sqlite3.Error as exc:
            record("collections_readable", False, f"could not read collections: {exc}")
            return ineligible("The collections table could not be read.")
    except sqlite3.Error as exc:
        record("sqlite_readable", False, f"SQLite read failed: {exc}")
        return ineligible(f"The palace database could not be read safely: {exc}")
    finally:
        conn.close()

    record("collections_present", bool(rows), f"{len(rows)} collection row(s)")
    if not rows:
        return ineligible("The collections table is empty; nothing to repair.")

    collection_names = [str(row[1]) for row in rows]

    # ── Untyped configuration must be exactly '{}' ────────────────────────────
    # NULL is deliberately rejected: the runtime opens a NULL config, so such a
    # palace is healthy and must not be mutated.
    typed_rows = 0
    untyped_rows = 0
    null_rows = 0
    empty_string_rows = 0
    other_rows = 0
    for _col_id, _name, raw_config in rows:
        if raw_config is None:
            null_rows += 1
            continue
        if not str(raw_config).strip():
            empty_string_rows += 1
            continue
        try:
            config = json.loads(raw_config)
        except (json.JSONDecodeError, TypeError):
            other_rows += 1
            continue
        if not isinstance(config, dict):
            other_rows += 1
        elif "_type" in config:
            typed_rows += 1
        elif config == {}:
            untyped_rows += 1
        else:
            other_rows += 1

    record(
        "no_null_config",
        null_rows == 0,
        "no NULL config_json_str"
        if null_rows == 0
        else f"{null_rows} NULL config_json_str value(s) — the runtime opens NULL, so no repair is needed",
    )
    if null_rows:
        return ineligible(
            "At least one collection has a NULL config_json_str. The stable runtime opens a NULL config, "
            "so this palace requires no repair and is deliberately left untouched."
        )

    record(
        "no_empty_string_config",
        empty_string_rows == 0,
        "no empty-string config_json_str"
        if empty_string_rows == 0
        else f"{empty_string_rows} empty-string config_json_str value(s)",
    )
    if empty_string_rows:
        return ineligible(
            "An empty-string configuration is a different failure shape than the supported legacy '{}' profile."
        )

    record(
        "no_unexpected_config",
        other_rows == 0,
        "every config_json_str is a JSON object"
        if other_rows == 0
        else f"{other_rows} config_json_str value(s) are invalid JSON or unexpectedly shaped",
    )
    if other_rows:
        return ineligible("At least one collection configuration is not the supported legacy shape.")

    record(
        "all_configs_untyped",
        untyped_rows == len(rows),
        f"{untyped_rows}/{len(rows)} untyped configuration(s)"
        + (f", {typed_rows} already typed" if typed_rows else ""),
    )
    if untyped_rows != len(rows):
        return ineligible(
            "Mixed or already-typed configurations detected; the narrow legacy repair does not apply."
        )

    # ── Storage profile (which schema generation wrote this palace?) ──────────
    profile_result = detect_storage_profile(path)
    schema_versions = dict(profile_result.schema_versions)
    for item in profile_result.evidence:
        record(f"profile.{item.name}", item.passed, item.detail)

    profile_known = profile_result.profile in (PROFILE_NATIVE_0_6, PROFILE_POST_1_X)
    record(
        "storage_profile_known",
        profile_known,
        PROFILE_LABELS.get(profile_result.profile, profile_result.profile)
        + ("" if profile_known else " — no supported legacy profile matched"),
    )
    if not profile_known:
        return ineligible(
            "The palace schema does not match a supported legacy repair profile; "
            "the narrow legacy repair does not apply.",
            schema_versions=schema_versions,
        )

    record(
        "expected_collection",
        expected in collection_names,
        f"expected collection {expected!r} among {collection_names}",
    )
    if expected not in collection_names:
        return ineligible(
            f"The expected MemPalace collection {expected!r} was not found in this palace.",
            profile=profile_result.profile,
            schema_versions=schema_versions,
        )

    return LegacyRepairEligibility(
        palace_path=str(path),
        eligible=True,
        collection_names=collection_names,
        invariants=invariants,
        message=(
            "Palace matches the narrow legacy repair contract for profile "
            f"{PROFILE_LABELS[profile_result.profile]} (untyped {LEGACY_UNTYPED_CONFIG})."
        ),
        profile=profile_result.profile,
        schema_versions=schema_versions,
    )


def _next_backup_path(db_path: Path, timestamp: datetime | None = None) -> Path:
    stamp = (timestamp or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    candidate = db_path.with_name(f"{db_path.name}.bak-{stamp}")
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = db_path.with_name(f"{db_path.name}.bak-{stamp}-{index}")
        if not candidate.exists():
            return candidate
        index += 1


def create_sqlite_backup(db_path: Path, timestamp: datetime | None = None) -> Path:
    """Create a consistent backup via the SQLite backup API. Never overwrites."""
    backup_path = _next_backup_path(db_path, timestamp)
    source = sqlite3.connect(_readonly_uri(db_path), uri=True)
    try:
        destination = sqlite3.connect(str(backup_path))
        try:
            with destination:
                source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    return backup_path


def default_connectivity_probe(palace_path: Path, collection_name: str) -> tuple[bool | None, str]:
    """Open the palace through ChromaDB and count drawers.

    Returns ``(None, detail)`` when ChromaDB is unavailable, so callers can treat
    that as "skipped" rather than a hard failure.
    """
    try:
        import chromadb
    except Exception as exc:  # pragma: no cover - environment dependent
        return None, f"chromadb unavailable ({exc})"

    try:
        client = chromadb.PersistentClient(path=str(palace_path))
        collection = client.get_or_create_collection(collection_name)
        return True, f"{collection.count()} drawers"
    except Exception as exc:
        return False, str(exc)


def repair_legacy_palace(
    palace_path: str | Path,
    *,
    expected_collection: str | None = None,
    config_provider: ConfigProvider | None = None,
    backup_factory: BackupFactory | None = None,
    connectivity_probe: ConnectivityProbe | None = None,
    write_manifest: bool = True,
    repo_root: Path | None = None,
) -> LegacyRepairReport:
    """Apply the narrow legacy repair, or explain why it is refused."""
    path = Path(palace_path).expanduser().resolve()
    db_path = path / CHROMA_SQLITE_FILENAME
    expected = expected_collection if expected_collection else _default_collection_name()

    eligibility = evaluate_legacy_repair_eligibility(path, expected_collection=expected)
    report = LegacyRepairReport(
        palace_path=str(path),
        status="ineligible",
        message=eligibility.message,
        detection_before=detect_palace_format(path).classification,
        profile=eligibility.profile,
        schema_versions=dict(eligibility.schema_versions),
    )
    if not eligibility.eligible:
        report.errors = [f"{item.name}: {item.detail}" for item in eligibility.failed_invariants()]
        return report

    provider = config_provider or default_config_provider
    try:
        correct_config = provider()
    except Exception as exc:
        report.status = "failed"
        report.message = "Could not compute the target typed configuration."
        report.errors = [str(exc)]
        return report

    # ── Backup (mandatory, never overwritten) ─────────────────────────────────
    try:
        backup_path = (backup_factory or create_sqlite_backup)(db_path)
    except Exception as exc:
        report.status = "failed"
        report.message = "Could not create the pre-repair SQLite backup; refusing to mutate."
        report.errors = [str(exc)]
        return report
    report.backup_path = str(backup_path)

    # ── Transactional mutation ────────────────────────────────────────────────
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(str(db_path))
        cursor = connection.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        # Eligibility already proved every collection carries an untyped '{}'
        # configuration (NULL and empty strings are rejected there), so every row
        # is a legitimate target. Never widen this: no generic repair.
        target_ids = []
        for col_id, _name in cursor.execute("SELECT id, name FROM collections"):
            target_ids.append(str(col_id))
            cursor.execute(
                "UPDATE collections SET config_json_str = ? WHERE id = ?",
                (correct_config, col_id),
            )
        connection.commit()
        report.updated_collections = target_ids
    except Exception as exc:
        if connection is not None:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
        report.status = "failed"
        report.message = "The legacy repair failed and was rolled back; the palace is unchanged."
        report.errors = [str(exc)]
        return report
    finally:
        if connection is not None:
            connection.close()

    report.detection_after = detect_palace_format(path).classification

    # ── Post-repair validation ────────────────────────────────────────────────
    validation_errors: list[str] = []
    if report.detection_after != CLASS_CHROMA_0_6:
        validation_errors.append(f"post-repair detection is {report.detection_after}, expected {CLASS_CHROMA_0_6}")

    try:
        check_conn = _open_readonly(db_path)
        try:
            integrity = check_conn.execute("PRAGMA integrity_check").fetchone()
            if not integrity or str(integrity[0]).lower() != "ok":
                validation_errors.append(f"post-repair integrity_check -> {integrity[0] if integrity else 'no result'}")
        finally:
            check_conn.close()
    except sqlite3.Error as exc:
        validation_errors.append(f"post-repair SQLite check failed: {exc}")

    probe = connectivity_probe or default_connectivity_probe
    reachable, detail = probe(path, expected)
    if reachable is False:
        validation_errors.append(f"palace is not readable after repair: {detail}")

    if validation_errors:
        report.errors = validation_errors
        restore_error = _restore_from_backup(backup_path, db_path)
        if restore_error is None:
            report.status = "restored"
            report.message = "Post-repair validation failed; the palace was restored from the backup."
        else:
            report.status = "failed"
            report.message = "Post-repair validation failed and the backup restore also failed."
            report.errors.append(restore_error)
        return report

    report.status = "repaired"
    report.message = (
        "Legacy palace repaired to the typed configuration (profile "
        f"{PROFILE_LABELS.get(report.profile, report.profile)})."
    )

    # ── Manifest (only after a successful repair and a real smoke test) ───────
    if write_manifest and reachable is not False:
        report.manifest_written = _write_manifest_best_effort(path, repo_root, report)

    return report


def _restore_from_backup(backup_path: Path, db_path: Path) -> str | None:
    try:
        for suffix in ("-wal", "-shm"):
            sidecar = db_path.with_name(db_path.name + suffix)
            if sidecar.exists():
                sidecar.unlink()
        source = sqlite3.connect(str(backup_path))
        try:
            destination = sqlite3.connect(str(db_path))
            try:
                with destination:
                    source.backup(destination)
            finally:
                destination.close()
        finally:
            source.close()
    except Exception as exc:
        return f"restore from {backup_path} failed: {exc}"
    return None


def _write_manifest_best_effort(palace_path: Path, repo_root: Path | None, report: LegacyRepairReport) -> bool:
    try:
        from palace_manifest import (
            MANIFEST_FILENAME as _MANIFEST_FILENAME,
            build_manifest,
            load_existing_manifest,
            write_manifest_file,
        )
    except Exception as exc:
        report.errors.append(f"manifest module unavailable: {exc}")
        return False

    manifest_path = palace_path / _MANIFEST_FILENAME
    root = repo_root if repo_root is not None else Path(__file__).resolve().parents[1]
    try:
        existing, _error = load_existing_manifest(manifest_path)
        if existing is not None:
            return False
        write_manifest_file(
            manifest_path,
            build_manifest(
                root,
                storage_profile=report.profile,
                schema_versions=report.schema_versions,
            ),
        )
    except Exception as exc:
        report.errors.append(f"could not write palace manifest: {exc}")
        return False
    return True


def run_health(
    palace_path: str | Path,
    mode: str,
    *,
    expected_collection: str | None = None,
    config_provider: ConfigProvider | None = None,
    connectivity_probe: ConnectivityProbe | None = None,
) -> tuple[str, bool]:
    """Single-entry health check used by scripts/check_palace_health.sh.

    Returns ``(token, ok)`` where ``token`` is one of the legacy shell tokens:
    ``OK:<count>``, ``FIXED:<names>|<backup>|<profile>``,
    ``REPAIRABLE:<names>|<profile>``, ``UNKNOWN:<reason>``, ``NOTFOUND:``,
    ``SKIP:<detail>`` or ``FAIL:<detail>``.
    """
    path = Path(palace_path).expanduser().resolve()
    db_path = path / CHROMA_SQLITE_FILENAME
    if mode not in {"repair", "read-only"}:
        raise ValueError(f"unsupported health mode: {mode!r}")

    if not db_path.exists():
        return "NOTFOUND:", True

    try:  # bootstrap not finished yet -> not an error
        import chromadb  # noqa: F401
        import mempalace  # noqa: F401
    except Exception as exc:
        return f"SKIP:{exc}", True

    expected = expected_collection if expected_collection else _default_collection_name()
    detection = detect_palace_format(path)

    if detection.classification == CLASS_CHROMA_0_6:
        probe = connectivity_probe or default_connectivity_probe
        reachable, detail = probe(path, expected)
        if reachable is True:
            match = re.match(r"\s*(\d+)", detail)
            return f"OK:{match.group(1) if match else ''}", True
        if reachable is None:
            return f"SKIP:{detail}", True
        return f"FAIL:{detail}", False

    eligibility = evaluate_legacy_repair_eligibility(path, expected_collection=expected)
    names = ",".join(eligibility.collection_names)

    if not eligibility.eligible:
        reasons = "; ".join(
            f"{item.name}: {item.detail}" for item in eligibility.failed_invariants()[:4]
        )
        return f"UNKNOWN:{reasons}", False

    if mode == "read-only":
        return f"REPAIRABLE:{names}|{eligibility.profile}", False

    report = repair_legacy_palace(
        path,
        expected_collection=expected,
        config_provider=config_provider,
        connectivity_probe=connectivity_probe,
        write_manifest=True,
    )
    if report.status == "repaired":
        return f"FIXED:{names}|{report.backup_path or ''}|{report.profile}", True

    detail = report.message
    if report.errors:
        detail = f"{detail} ({'; '.join(report.errors)})"
    return f"FAIL:{detail}", False


def _print_eligibility(eligibility: LegacyRepairEligibility, as_json: bool) -> None:
    if as_json:
        json.dump(eligibility.to_json_dict(), sys.stdout, indent=2)
        print()
        return

    verdict = "ELIGIBLE" if eligibility.eligible else "NOT ELIGIBLE"
    print(f"[{'OK' if eligibility.eligible else 'ERROR'}] Legacy repair {verdict}: {eligibility.palace_path}")
    print(f"        storage profile: {PROFILE_LABELS.get(eligibility.profile, eligibility.profile)}")
    if eligibility.schema_versions:
        print(f"        schema versions: {eligibility.schema_versions}")
    print(f"        {eligibility.message}")
    for item in eligibility.invariants:
        marker = "pass" if item.passed else "FAIL"
        print(f"        [{marker}] {item.name}: {item.detail}")


def _print_profile(profile: StorageProfileResult, as_json: bool) -> None:
    if as_json:
        json.dump(profile.to_json_dict(), sys.stdout, indent=2)
        print()
        return

    print(f"[INFO]  Storage profile: {PROFILE_LABELS.get(profile.profile, profile.profile)}")
    print(f"        palace: {profile.palace_path}")
    print(f"        confidence: {profile.confidence}")
    if profile.schema_versions:
        print(f"        schema versions: {profile.schema_versions}")
    for item in profile.evidence:
        marker = "pass" if item.passed else "FAIL"
        print(f"        [{marker}] {item.name}: {item.detail}")


def _print_report(report: LegacyRepairReport, as_json: bool) -> None:
    if as_json:
        json.dump(report.to_json_dict(), sys.stdout, indent=2)
        print()
        return

    print(f"[{report.status.upper()}] {report.message}")
    print(f"        palace: {report.palace_path}")
    if report.profile and report.profile != PROFILE_UNKNOWN:
        print(f"        storage profile: {PROFILE_LABELS.get(report.profile, report.profile)}")
    if report.schema_versions:
        print(f"        schema versions: {report.schema_versions}")
    if report.backup_path:
        print(f"        backup: {report.backup_path}")
    if report.updated_collections:
        print(f"        repaired collections: {', '.join(report.updated_collections)}")
    if report.detection_before or report.detection_after:
        print(f"        format: {report.detection_before} -> {report.detection_after or 'n/a'}")
    if report.manifest_written:
        print("        manifest: written")
    for error in report.errors:
        print(f"        !! {error}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight (and optionally apply) the narrow legacy repair that rewrites an "
            "untyped collections.config_json_str '{}' into the typed 0.6.x configuration."
        )
    )
    parser.add_argument("palace_path", nargs="?", default=_default_palace_path())
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the repair. Without it, only the read-only preflight is reported.",
    )
    parser.add_argument(
        "--detect-profile",
        action="store_true",
        help=(
            "Only report the structural storage profile "
            "(chroma_0_6_native / chroma_1_x_migrated / unknown). No mutation."
        ),
    )
    parser.add_argument(
        "--health",
        choices=("repair", "read-only"),
        default=None,
        help="Internal mode used by check_palace_health.sh; prints a single status token.",
    )
    parser.add_argument(
        "--expected-collection",
        default=None,
        help=f"Collection name that must be present (default: {DEFAULT_COLLECTION_NAME})",
    )
    parser.add_argument(
        "--no-write-manifest",
        action="store_true",
        help="Do not write mempalace-bridge-manifest.json after a successful repair.",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root used for the manifest bridge version.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    if args.detect_profile:
        _print_profile(detect_storage_profile(args.palace_path), args.json)
        return 0

    if args.health is not None:
        token, ok = run_health(
            args.palace_path,
            args.health,
            expected_collection=args.expected_collection,
        )
        print(token)
        return 0 if ok else 1

    if not args.apply:
        eligibility = evaluate_legacy_repair_eligibility(
            args.palace_path, expected_collection=args.expected_collection
        )
        _print_eligibility(eligibility, args.json)
        return 0 if eligibility.eligible else 1

    report = repair_legacy_palace(
        args.palace_path,
        expected_collection=args.expected_collection,
        write_manifest=not args.no_write_manifest,
        repo_root=Path(args.repo_root) if args.repo_root else None,
    )
    _print_report(report, args.json)
    return 0 if report.status == "repaired" else 1


if __name__ == "__main__":
    raise SystemExit(main())
