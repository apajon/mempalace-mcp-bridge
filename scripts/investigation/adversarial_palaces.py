#!/usr/bin/env python3
"""Generate adversarial palace fixtures for migration robustness testing.

Each generator creates a self-contained 0.6.x-format palace with a specific
class of defect, then returns metadata about what was injected.

All palaces are SQLite-backed with a bridge manifest so the format detector
classifies them as chroma_0_6.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

MANIFEST_CONTENT = {
    "compatibility_line": "chromadb-0.6.x",
    "chromadb_version": "0.6.3",
}


def _init_palace(palace: Path) -> sqlite3.Connection:
    palace.mkdir(parents=True, exist_ok=True)
    (palace / "mempalace-bridge-manifest.json").write_text(
        json.dumps(MANIFEST_CONTENT),
        encoding="utf-8",
    )
    conn = sqlite3.connect(palace / "chroma.sqlite3")
    cur = conn.cursor()
    cur.execute("CREATE TABLE embeddings (id INTEGER PRIMARY KEY, embedding_id TEXT)")
    cur.execute(
        """
        CREATE TABLE embedding_metadata (
            id INTEGER,
            key TEXT,
            string_value TEXT,
            int_value INTEGER,
            float_value REAL,
            bool_value INTEGER
        )
        """
    )
    return conn


def _insert_drawer(
    conn: sqlite3.Connection,
    row_id: int,
    drawer_id: str,
    document: str,
    metadata: dict[str, Any],
) -> None:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO embeddings (id, embedding_id) VALUES (?, ?)",
        (row_id, drawer_id),
    )
    cur.execute(
        "INSERT INTO embedding_metadata (id, key, string_value) VALUES (?, 'chroma:document', ?)",
        (row_id, document),
    )
    for key, value in metadata.items():
        if isinstance(value, bool):
            cur.execute(
                "INSERT INTO embedding_metadata (id, key, bool_value) VALUES (?, ?, ?)",
                (row_id, key, int(value)),
            )
        elif isinstance(value, int):
            cur.execute(
                "INSERT INTO embedding_metadata (id, key, int_value) VALUES (?, ?, ?)",
                (row_id, key, value),
            )
        elif isinstance(value, float):
            cur.execute(
                "INSERT INTO embedding_metadata (id, key, float_value) VALUES (?, ?, ?)",
                (row_id, key, value),
            )
        else:
            cur.execute(
                "INSERT INTO embedding_metadata (id, key, string_value) VALUES (?, ?, ?)",
                (row_id, key, str(value)),
            )


# --- Valid baseline (control group) ---


def gen_valid_baseline(root: Path) -> dict[str, Any]:
    """Minimal valid palace — 3 clean drawers."""
    palace = root / "valid_baseline"
    conn = _init_palace(palace)
    _insert_drawer(
        conn,
        1,
        "d1",
        "Architecture overview for the bridge project",
        {"wing": "proj", "room": "docs", "chunk_index": 0},
    )
    _insert_drawer(
        conn, 2, "d2", "Implementation notes on MCP server startup", {"wing": "proj", "room": "code", "chunk_index": 1}
    )
    _insert_drawer(
        conn,
        3,
        "d3",
        "Troubleshooting guide for ChromaDB issues",
        {"wing": "shared", "room": "notes", "chunk_index": 2},
    )
    conn.commit()
    conn.close()
    return {"palace": str(palace), "case": "valid_baseline", "defect": None, "drawer_count": 3}


# --- Missing metadata fields ---


def gen_missing_metadata(root: Path) -> dict[str, Any]:
    """Drawers with partial or completely missing metadata fields."""
    palace = root / "missing_metadata"
    conn = _init_palace(palace)
    # Normal drawer
    _insert_drawer(
        conn, 1, "d1", "Normal drawer with full metadata", {"wing": "proj", "room": "docs", "chunk_index": 0}
    )
    # No wing
    _insert_drawer(conn, 2, "d2", "Drawer missing wing field", {"room": "code", "chunk_index": 1})
    # No room
    _insert_drawer(conn, 3, "d3", "Drawer missing room field", {"wing": "proj", "chunk_index": 2})
    # No wing, no room
    _insert_drawer(conn, 4, "d4", "Drawer missing both wing and room", {"chunk_index": 3})
    # Completely empty metadata
    _insert_drawer(conn, 5, "d5", "Drawer with no metadata at all", {})
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "missing_metadata",
        "defect": "missing wing/room/all metadata fields",
        "drawer_count": 5,
    }


# --- Inconsistent wing/room structure ---


def gen_inconsistent_wing_room(root: Path) -> dict[str, Any]:
    """Wings and rooms with unusual naming: empty strings, special chars, very long names."""
    palace = root / "inconsistent_wing_room"
    conn = _init_palace(palace)
    _insert_drawer(conn, 1, "d1", "Normal drawer", {"wing": "proj", "room": "docs", "chunk_index": 0})
    _insert_drawer(conn, 2, "d2", "Empty string wing", {"wing": "", "room": "docs", "chunk_index": 1})
    _insert_drawer(conn, 3, "d3", "Empty string room", {"wing": "proj", "room": "", "chunk_index": 2})
    _insert_drawer(conn, 4, "d4", "Both empty", {"wing": "", "room": "", "chunk_index": 3})
    _insert_drawer(
        conn, 5, "d5", "Wing with special chars", {"wing": "proj/sub\\path", "room": "docs<>test", "chunk_index": 4}
    )
    _insert_drawer(
        conn, 6, "d6", "Very long wing name " * 10, {"wing": "a" * 500, "room": "b" * 500, "chunk_index": 5}
    )
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "inconsistent_wing_room",
        "defect": "empty/special/long wing/room names",
        "drawer_count": 6,
    }


# --- Duplicated IDs ---


def gen_duplicate_ids(root: Path) -> dict[str, Any]:
    """Multiple embeddings rows sharing the same embedding_id."""
    palace = root / "duplicate_ids"
    conn = _init_palace(palace)
    _insert_drawer(conn, 1, "d1", "First instance of d1", {"wing": "proj", "room": "docs", "chunk_index": 0})
    _insert_drawer(
        conn, 2, "d1", "Second instance of d1 (duplicate)", {"wing": "proj", "room": "code", "chunk_index": 1}
    )
    _insert_drawer(conn, 3, "d2", "Normal drawer d2", {"wing": "proj", "room": "docs", "chunk_index": 2})
    _insert_drawer(conn, 4, "d3", "Normal drawer d3", {"wing": "shared", "room": "notes", "chunk_index": 3})
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "duplicate_ids",
        "defect": "embedding_id 'd1' appears twice",
        "drawer_count": 4,
    }


# --- Blank / null IDs ---


def gen_blank_ids(root: Path) -> dict[str, Any]:
    """Embeddings with NULL or empty-string IDs."""
    palace = root / "blank_ids"
    conn = _init_palace(palace)
    cur = conn.cursor()
    # Normal drawer
    _insert_drawer(conn, 1, "d1", "Normal drawer", {"wing": "proj", "room": "docs", "chunk_index": 0})
    # NULL embedding_id
    cur.execute("INSERT INTO embeddings (id, embedding_id) VALUES (2, NULL)")
    cur.execute(
        "INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'chroma:document', 'Drawer with NULL id')"
    )
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'wing', 'proj')")
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'room', 'code')")
    # Empty-string embedding_id
    cur.execute("INSERT INTO embeddings (id, embedding_id) VALUES (3, '')")
    cur.execute(
        "INSERT INTO embedding_metadata (id, key, string_value) VALUES (3, 'chroma:document', 'Drawer with empty id')"
    )
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (3, 'wing', 'proj')")
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (3, 'room', 'docs')")
    # Whitespace-only embedding_id
    cur.execute("INSERT INTO embeddings (id, embedding_id) VALUES (4, '   ')")
    cur.execute(
        "INSERT INTO embedding_metadata (id, key, string_value) VALUES (4, 'chroma:document', 'Drawer with whitespace id')"
    )
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (4, 'wing', 'shared')")
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (4, 'room', 'notes')")
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "blank_ids",
        "defect": "NULL, empty, and whitespace-only embedding_ids",
        "drawer_count": 4,
    }


# --- Partial corruption: missing chroma:document ---


def gen_missing_document(root: Path) -> dict[str, Any]:
    """Some rows have no chroma:document entry in embedding_metadata."""
    palace = root / "missing_document"
    conn = _init_palace(palace)
    cur = conn.cursor()
    _insert_drawer(conn, 1, "d1", "Normal drawer with document", {"wing": "proj", "room": "docs", "chunk_index": 0})
    _insert_drawer(conn, 2, "d2", "Another normal drawer", {"wing": "proj", "room": "code", "chunk_index": 1})
    # d3 has id and metadata but NO chroma:document
    cur.execute("INSERT INTO embeddings (id, embedding_id) VALUES (3, 'd3')")
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (3, 'wing', 'proj')")
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (3, 'room', 'docs')")
    cur.execute("INSERT INTO embedding_metadata (id, key, int_value) VALUES (3, 'chunk_index', 2)")
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "missing_document",
        "defect": "drawer d3 has no chroma:document entry",
        "drawer_count": 3,
    }


# --- Multiple chroma:document entries per row ---


def gen_duplicate_document_entries(root: Path) -> dict[str, Any]:
    """A single row with multiple chroma:document entries."""
    palace = root / "duplicate_document_entries"
    conn = _init_palace(palace)
    cur = conn.cursor()
    _insert_drawer(conn, 1, "d1", "Normal drawer", {"wing": "proj", "room": "docs", "chunk_index": 0})
    # d2 has two chroma:document entries
    cur.execute("INSERT INTO embeddings (id, embedding_id) VALUES (2, 'd2')")
    cur.execute(
        "INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'chroma:document', 'First document text')"
    )
    cur.execute(
        "INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'chroma:document', 'Second document text (conflicting)')"
    )
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'wing', 'proj')")
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'room', 'code')")
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "duplicate_document_entries",
        "defect": "d2 has 2 chroma:document entries",
        "drawer_count": 2,
    }


# --- Duplicate metadata keys ---


def gen_duplicate_metadata_keys(root: Path) -> dict[str, Any]:
    """A row with duplicated metadata keys (not chroma:*)."""
    palace = root / "duplicate_metadata_keys"
    conn = _init_palace(palace)
    cur = conn.cursor()
    _insert_drawer(conn, 1, "d1", "Normal drawer", {"wing": "proj", "room": "docs", "chunk_index": 0})
    # d2 has 'wing' written twice
    cur.execute("INSERT INTO embeddings (id, embedding_id) VALUES (2, 'd2')")
    cur.execute(
        "INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'chroma:document', 'Drawer with dup metadata key')"
    )
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'wing', 'proj')")
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'wing', 'shared')")
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'room', 'docs')")
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "duplicate_metadata_keys",
        "defect": "d2 has 'wing' duplicated",
        "drawer_count": 2,
    }


# --- Edge unicode / encoding ---


def gen_unicode_edge_cases(root: Path) -> dict[str, Any]:
    """Documents and metadata with unusual Unicode content."""
    palace = root / "unicode_edge_cases"
    conn = _init_palace(palace)
    # Emoji-heavy
    _insert_drawer(
        conn, 1, "d1", "🔥🚀💡 Architecture with emoji 🏗️✨", {"wing": "proj_🏠", "room": "docs_📄", "chunk_index": 0}
    )
    # CJK
    _insert_drawer(
        conn, 2, "d2", "这是一个中文文档关于内存宫殿的架构", {"wing": "中文翼", "room": "文档室", "chunk_index": 1}
    )
    # RTL Arabic
    _insert_drawer(
        conn, 3, "d3", "هذا مستند عربي حول بنية قصر الذاكرة", {"wing": "عربي", "room": "مستندات", "chunk_index": 2}
    )
    # Combining diacritics
    _insert_drawer(
        conn,
        4,
        "d4",
        "Café résumé naïve über Zürich — combining marks: a\u0301 e\u0301",
        {"wing": "accénts", "room": "diacritics", "chunk_index": 3},
    )
    # Zero-width chars
    _insert_drawer(
        conn,
        5,
        "d5",
        "Text with\u200bzero\u200bwidth\u200bspaces and\u200cjoiner\u200dchars",
        {"wing": "invi\u200bsible", "room": "z\u200cwj", "chunk_index": 4},
    )
    # Null byte in text (stored as string)
    _insert_drawer(
        conn,
        6,
        "d6",
        "Text with embedded null \x00 byte in middle",
        {"wing": "proj", "room": "null_byte", "chunk_index": 5},
    )
    # Surrogate-safe: 4-byte emoji sequences
    _insert_drawer(
        conn, 7, "d7", "Family emoji: 👨‍👩‍👧‍👦 and flag: 🏳️‍🌈", {"wing": "proj", "room": "astral", "chunk_index": 6}
    )
    # Very long single line
    _insert_drawer(conn, 8, "d8", "A" * 100_000, {"wing": "proj", "room": "long", "chunk_index": 7})
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "unicode_edge_cases",
        "defect": "emoji/CJK/RTL/diacritics/zero-width/null-byte/astral/100K",
        "drawer_count": 8,
    }


# --- Very large content ---


def gen_large_content(root: Path) -> dict[str, Any]:
    """Drawers with very large documents."""
    palace = root / "large_content"
    conn = _init_palace(palace)
    _insert_drawer(
        conn, 1, "d1", "Normal sized document for reference", {"wing": "proj", "room": "docs", "chunk_index": 0}
    )
    # 1MB document
    _insert_drawer(conn, 2, "d2", "X" * 1_000_000, {"wing": "proj", "room": "mega", "chunk_index": 1})
    # 10MB document
    _insert_drawer(conn, 3, "d3", "Y" * 10_000_000, {"wing": "proj", "room": "mega", "chunk_index": 2})
    # Many newlines
    _insert_drawer(
        conn,
        4,
        "d4",
        "\n".join(f"line {i}: content about architecture" for i in range(10_000)),
        {"wing": "proj", "room": "multiline", "chunk_index": 3},
    )
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "large_content",
        "defect": "1MB + 10MB + 10K-line documents",
        "drawer_count": 4,
    }


# --- Empty palace (no drawers) ---


def gen_empty_palace(root: Path) -> dict[str, Any]:
    """Valid palace structure but no embedding rows."""
    palace = root / "empty_palace"
    conn = _init_palace(palace)
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "empty_palace",
        "defect": "zero drawers in embeddings table",
        "drawer_count": 0,
    }


# --- Missing sqlite file ---


def gen_missing_sqlite(root: Path) -> dict[str, Any]:
    """Palace directory with manifest but no chroma.sqlite3."""
    palace = root / "missing_sqlite"
    palace.mkdir(parents=True, exist_ok=True)
    (palace / "mempalace-bridge-manifest.json").write_text(
        json.dumps(MANIFEST_CONTENT),
        encoding="utf-8",
    )
    return {"palace": str(palace), "case": "missing_sqlite", "defect": "no chroma.sqlite3 file", "drawer_count": 0}


# --- Corrupted sqlite ---


def gen_corrupted_sqlite(root: Path) -> dict[str, Any]:
    """Palace with a corrupted (non-sqlite) chroma.sqlite3 file."""
    palace = root / "corrupted_sqlite"
    palace.mkdir(parents=True, exist_ok=True)
    (palace / "mempalace-bridge-manifest.json").write_text(
        json.dumps(MANIFEST_CONTENT),
        encoding="utf-8",
    )
    (palace / "chroma.sqlite3").write_bytes(b"THIS IS NOT A SQLITE DATABASE\x00\xff\xfe")
    return {
        "palace": str(palace),
        "case": "corrupted_sqlite",
        "defect": "chroma.sqlite3 is not a valid SQLite file",
        "drawer_count": 0,
    }


# --- Wrong schema (missing tables) ---


def gen_wrong_schema(root: Path) -> dict[str, Any]:
    """Palace with valid SQLite but wrong table schema."""
    palace = root / "wrong_schema"
    palace.mkdir(parents=True, exist_ok=True)
    (palace / "mempalace-bridge-manifest.json").write_text(
        json.dumps(MANIFEST_CONTENT),
        encoding="utf-8",
    )
    conn = sqlite3.connect(palace / "chroma.sqlite3")
    conn.execute("CREATE TABLE some_other_table (id INTEGER PRIMARY KEY, data TEXT)")
    conn.execute("INSERT INTO some_other_table VALUES (1, 'not a palace')")
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "wrong_schema",
        "defect": "SQLite has wrong table schema (no embeddings/embedding_metadata)",
        "drawer_count": 0,
    }


# --- Mixed old/new format indicators ---


def gen_mixed_format_signals(root: Path) -> dict[str, Any]:
    """Manifest says 0.6.x but sqlite has tables hinting at 1.x structure."""
    palace = root / "mixed_format_signals"
    conn = _init_palace(palace)
    _insert_drawer(
        conn, 1, "d1", "Drawer from mixed-signal palace", {"wing": "proj", "room": "docs", "chunk_index": 0}
    )
    _insert_drawer(conn, 2, "d2", "Second drawer in mixed palace", {"wing": "proj", "room": "code", "chunk_index": 1})
    # Add a table that looks like 1.x schema (tenants table)
    conn.execute("CREATE TABLE tenants (id TEXT PRIMARY KEY, topic TEXT)")
    conn.execute("INSERT INTO tenants VALUES ('default_tenant', 'default_topic')")
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "mixed_format_signals",
        "defect": "0.6.x manifest but extra 1.x-style tables",
        "drawer_count": 2,
    }


# --- No manifest file ---


def gen_no_manifest(root: Path) -> dict[str, Any]:
    """Palace with valid 0.6.x SQLite but no bridge manifest."""
    palace = root / "no_manifest"
    palace.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(palace / "chroma.sqlite3")
    cur = conn.cursor()
    cur.execute("CREATE TABLE embeddings (id INTEGER PRIMARY KEY, embedding_id TEXT)")
    cur.execute(
        """CREATE TABLE embedding_metadata (
            id INTEGER, key TEXT, string_value TEXT,
            int_value INTEGER, float_value REAL, bool_value INTEGER)""",
    )
    cur.execute("INSERT INTO embeddings VALUES (1, 'd1')")
    cur.execute(
        "INSERT INTO embedding_metadata (id, key, string_value) VALUES (1, 'chroma:document', 'Doc without manifest')"
    )
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (1, 'wing', 'proj')")
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (1, 'room', 'docs')")
    cur.execute("INSERT INTO embeddings VALUES (2, 'd2')")
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'chroma:document', 'Another doc')")
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'wing', 'proj')")
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (2, 'room', 'code')")
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "no_manifest",
        "defect": "no bridge manifest (structural detection only)",
        "drawer_count": 2,
    }


# --- Conflicting manifest ---


def gen_conflicting_manifest(root: Path) -> dict[str, Any]:
    """Manifest with conflicting compatibility_line and chromadb_version."""
    palace = root / "conflicting_manifest"
    palace.mkdir(parents=True, exist_ok=True)
    conflicting = {
        "compatibility_line": "chromadb-0.6.x",
        "chromadb_version": "1.5.7",
    }
    (palace / "mempalace-bridge-manifest.json").write_text(
        json.dumps(conflicting),
        encoding="utf-8",
    )
    conn = sqlite3.connect(palace / "chroma.sqlite3")
    cur = conn.cursor()
    cur.execute("CREATE TABLE embeddings (id INTEGER PRIMARY KEY, embedding_id TEXT)")
    cur.execute(
        """CREATE TABLE embedding_metadata (
            id INTEGER, key TEXT, string_value TEXT,
            int_value INTEGER, float_value REAL, bool_value INTEGER)""",
    )
    cur.execute("INSERT INTO embeddings VALUES (1, 'd1')")
    cur.execute(
        "INSERT INTO embedding_metadata (id, key, string_value) VALUES (1, 'chroma:document', 'Conflicting manifest drawer')"
    )
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (1, 'wing', 'proj')")
    cur.execute("INSERT INTO embedding_metadata (id, key, string_value) VALUES (1, 'room', 'docs')")
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "conflicting_manifest",
        "defect": "manifest says 0.6.x line but 1.5.7 version",
        "drawer_count": 1,
    }


# --- Single-drawer palace ---


def gen_single_drawer(root: Path) -> dict[str, Any]:
    """Minimal palace with exactly one drawer."""
    palace = root / "single_drawer"
    conn = _init_palace(palace)
    _insert_drawer(
        conn, 1, "only_one", "The sole drawer in this palace", {"wing": "solo", "room": "only", "chunk_index": 0}
    )
    conn.commit()
    conn.close()
    return {"palace": str(palace), "case": "single_drawer", "defect": None, "drawer_count": 1}


# --- Metadata type edge cases ---


def gen_metadata_type_edge(root: Path) -> dict[str, Any]:
    """Metadata with edge-case types: very large ints, floats, booleans, empty strings."""
    palace = root / "metadata_type_edge"
    conn = _init_palace(palace)
    _insert_drawer(conn, 1, "d1", "Normal drawer", {"wing": "proj", "room": "docs", "chunk_index": 0})
    _insert_drawer(conn, 2, "d2", "Large int metadata", {"wing": "proj", "room": "code", "chunk_index": 2**62})
    _insert_drawer(conn, 3, "d3", "Float metadata", {"wing": "proj", "room": "code", "chunk_index": 3.14159})
    _insert_drawer(
        conn,
        4,
        "d4",
        "Boolean metadata",
        {"wing": "proj", "room": "code", "is_active": True, "is_deleted": False, "chunk_index": 0},
    )
    _insert_drawer(conn, 5, "d5", "Empty string metadata value", {"wing": "", "room": "", "tag": "", "chunk_index": 0})
    _insert_drawer(conn, 6, "d6", "Negative int metadata", {"wing": "proj", "room": "code", "chunk_index": -42})
    _insert_drawer(conn, 7, "d7", "Float NaN-like metadata", {"wing": "proj", "room": "code", "score": float("inf")})
    conn.commit()
    conn.close()
    return {
        "palace": str(palace),
        "case": "metadata_type_edge",
        "defect": "large int/float/bool/empty/negative/inf metadata values",
        "drawer_count": 7,
    }


# --- Registry of all generators ---

ALL_GENERATORS = [
    gen_valid_baseline,
    gen_missing_metadata,
    gen_inconsistent_wing_room,
    gen_duplicate_ids,
    gen_blank_ids,
    gen_missing_document,
    gen_duplicate_document_entries,
    gen_duplicate_metadata_keys,
    gen_unicode_edge_cases,
    gen_large_content,
    gen_empty_palace,
    gen_missing_sqlite,
    gen_corrupted_sqlite,
    gen_wrong_schema,
    gen_mixed_format_signals,
    gen_no_manifest,
    gen_conflicting_manifest,
    gen_single_drawer,
    gen_metadata_type_edge,
]


if __name__ == "__main__":
    import sys
    import tempfile

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="adversarial_"))
    print(f"Generating adversarial palaces in: {root}")
    for gen_fn in ALL_GENERATORS:
        info = gen_fn(root)
        print(f"  [{info['case']}] drawers={info['drawer_count']}  defect={info['defect']}")
    print(f"\n{len(ALL_GENERATORS)} adversarial palaces generated.")
