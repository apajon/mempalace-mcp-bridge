"""Shared palace fixtures for the legacy-repair tests.

Design rules (important):

* every fixture is built from a **real ChromaDB palace** created inside a
  temporary directory — a real user palace is never touched;
* each fixture reproduces a *documented storage profile*, so the tests exercise
  the profiles the bridge claims to support instead of only the one palace that
  happened to be observed on the developer's machine;
* mutations are applied with raw SQLite on purpose: they simulate what a
  different ChromaDB generation did to the file, which is exactly the situation
  the repair has to recognise.

Profiles:

``chroma_0_6_native``
    What ChromaDB 0.6.3 itself produces (``sysdb 9`` / ``metadb 4`` /
    ``embeddings_queue 2``, blob ``seq_id``, no ``schema_str``). A pre-0.6 palace
    migrated up to 0.6.x ends up in this shape, and the bridge documentation
    describes it as the historical ``{}`` case.

``chroma_1_x_migrated``
    What ChromaDB 1.x produces (``sysdb 10`` / ``metadb 6`` / integer ``seq_id``,
    ``schema_str``, ``acquire_write``, ``embedding_metadata_array``). A palace
    that was opened by 1.x and then reopened by the pinned 0.6.x ends up here.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

TYPED_CONFIG = json.dumps({"_type": "CollectionConfigurationInternal"})
COLLECTION_NAME = "mempalace_drawers"
DRAWER_COUNT = 5

# Structural expectations, kept next to the fixtures so the tests can assert
# against the same numbers the module uses without importing private helpers.
NATIVE_0_6_MIGRATIONS = {"sysdb": 9, "metadb": 4, "embeddings_queue": 2}
POST_1_X_MIGRATIONS = {"sysdb": 10, "metadb": 6, "embeddings_queue": 2}


def require_chromadb():
    import chromadb

    return chromadb


# ─── Creation ────────────────────────────────────────────────────────────────


def create_typed_palace(
    palace: Path,
    *,
    rows: int = DRAWER_COUNT,
    collection_name: str = COLLECTION_NAME,
) -> Path:
    """Create a genuine, healthy palace with the pinned ChromaDB line."""
    chromadb = require_chromadb()
    client = chromadb.PersistentClient(path=str(palace))
    collection = client.create_collection(collection_name)
    collection.add(
        ids=[f"d{index}" for index in range(rows)],
        embeddings=[[0.1 * (index + 1)] * 8 for index in range(rows)],
        documents=[f"doc{index}" for index in range(rows)],
    )
    del client, collection
    return palace / "chroma.sqlite3"


def build_healthy_native_palace(palace: Path, **kwargs) -> Path:
    """A healthy, typed palace of the pinned line (needs no repair)."""
    create_typed_palace(palace, **kwargs)
    return palace


def build_native_0_6_legacy_palace(palace: Path, **kwargs) -> Path:
    """Profile A — native 0.6.x schema with an untyped ``{}`` configuration."""
    create_typed_palace(palace, **kwargs)
    set_config_value(palace, "{}")
    return palace


def build_post_1_x_legacy_palace(palace: Path, **kwargs) -> Path:
    """Profile B — 1.x-migrated schema with an untyped ``{}`` configuration."""
    create_typed_palace(palace, **kwargs)
    apply_post_1_x_migration_steps(palace)
    set_config_value(palace, "{}")
    return palace


def apply_post_1_x_migration_steps(palace: Path) -> None:
    """Apply the schema steps ChromaDB 1.x performs on an existing palace."""
    conn = _connect(palace)
    cur = conn.cursor()

    # metadb 5 — convert seq_id blobs to native integers.
    for new_id, (embedding_id,) in enumerate(
        list(cur.execute("SELECT id FROM embeddings ORDER BY id")), start=1
    ):
        cur.execute("UPDATE embeddings SET seq_id=? WHERE id=?", (new_id, embedding_id))
    cur.execute("ALTER TABLE max_seq_id ADD COLUMN int_seq_id INTEGER")
    cur.execute("UPDATE max_seq_id SET int_seq_id=(SELECT MAX(seq_id) FROM embeddings)")
    cur.execute("ALTER TABLE max_seq_id DROP COLUMN seq_id")
    cur.execute("ALTER TABLE max_seq_id RENAME COLUMN int_seq_id TO seq_id")
    cur.execute(
        "INSERT INTO migrations VALUES ('metadb',5,'00005-max-seq-id-int.sqlite.sql','','h5')"
    )

    # metadb 6 — exploded array metadata support.
    cur.execute(
        "CREATE TABLE IF NOT EXISTS embedding_metadata_array ("
        "id INTEGER NOT NULL, key TEXT NOT NULL, string_value TEXT, "
        "int_value INTEGER, float_value REAL, bool_value INTEGER)"
    )
    cur.execute(
        "INSERT INTO migrations VALUES "
        "('metadb',6,'00006-metadata-array-support.sqlite.sql','','h6')"
    )

    # sysdb 10 — collection schema string.
    cur.execute("ALTER TABLE collections ADD COLUMN schema_str TEXT")
    cur.execute("UPDATE collections SET schema_str=?", (json.dumps({"defaults": {}}),))
    cur.execute(
        "INSERT INTO migrations VALUES ('sysdb',10,'00010-collection-schema.sqlite.sql','','h10')"
    )

    # 1.x write-lock table.
    cur.execute("CREATE TABLE IF NOT EXISTS acquire_write (id INTEGER PRIMARY KEY, lock TEXT)")
    conn.commit()
    conn.close()


# ─── Mutations used by the negative tests ────────────────────────────────────


def _connect(palace: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(palace / "chroma.sqlite3"))


def set_config_value(palace: Path, value: str | None) -> None:
    conn = _connect(palace)
    conn.execute("UPDATE collections SET config_json_str=?", (value,))
    conn.commit()
    conn.close()


def read_config_value(palace: Path) -> str | None:
    db_path = (palace / "chroma.sqlite3").resolve()
    conn = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT config_json_str FROM collections").fetchone()[0]
    finally:
        conn.close()


def add_extra_collection(palace: Path, name: str, config_json: str) -> None:
    conn = _connect(palace)
    if _has_schema_str(conn):
        conn.execute(
            "INSERT INTO collections VALUES (?,?,?,?,?,?)",
            (f"extra-{name}", name, 384, "db-1", config_json, json.dumps({"defaults": {}})),
        )
    else:
        conn.execute(
            "INSERT INTO collections VALUES (?,?,?,?,?)",
            (f"extra-{name}", name, 384, "db-1", config_json),
        )
    conn.commit()
    conn.close()


def _has_schema_str(conn: sqlite3.Connection) -> bool:
    return "schema_str" in {row[1] for row in conn.execute("PRAGMA table_info(collections)")}


def set_migrations(palace: Path, versions: dict[str, int]) -> None:
    conn = _connect(palace)
    conn.execute("DELETE FROM migrations")
    for directory, version in versions.items():
        conn.execute(
            "INSERT INTO migrations VALUES (?,?,?,?,?)",
            (directory, version, f"{version}.sql", "", "h"),
        )
    conn.commit()
    conn.close()


def drop_table(palace: Path, name: str) -> None:
    conn = _connect(palace)
    conn.execute(f"DROP TABLE {name}")
    conn.commit()
    conn.close()


def add_foreign_table(palace: Path, name: str) -> None:
    conn = _connect(palace)
    conn.execute(f"CREATE TABLE IF NOT EXISTS {name} (meta TEXT)")
    conn.commit()
    conn.close()


def convert_seq_id_to_integer(palace: Path) -> None:
    """Apply only the metadb 5 seq_id conversion (partial migration)."""
    conn = _connect(palace)
    cur = conn.cursor()
    for new_id, (embedding_id,) in enumerate(
        list(cur.execute("SELECT id FROM embeddings ORDER BY id")), start=1
    ):
        cur.execute("UPDATE embeddings SET seq_id=? WHERE id=?", (new_id, embedding_id))
    cur.execute("CREATE TABLE max_seq_id_new (segment_id TEXT PRIMARY KEY, seq_id INTEGER)")
    cur.execute("INSERT INTO max_seq_id_new SELECT segment_id, (SELECT MAX(seq_id) FROM embeddings) FROM max_seq_id")
    cur.execute("DROP TABLE max_seq_id")
    cur.execute("ALTER TABLE max_seq_id_new RENAME TO max_seq_id")
    conn.commit()
    conn.close()


def write_manifest(palace: Path, payload: dict[str, object]) -> None:
    (palace / "mempalace-bridge-manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def write_manifest_text(palace: Path, raw: str) -> None:
    (palace / "mempalace-bridge-manifest.json").write_text(raw, encoding="utf-8")


def corrupt_database(palace: Path) -> None:
    db_path = palace / "chroma.sqlite3"
    raw = bytearray(db_path.read_bytes())
    start = len(raw) // 2
    for offset in range(start, min(len(raw), start + 4096)):
        raw[offset] = 0xFF
    db_path.write_bytes(bytes(raw))
