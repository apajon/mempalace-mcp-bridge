#!/usr/bin/env python3
"""
Cross-version _type failure reproduction.

Creates a palace under chromadb 1.5.7, then shows what 0.6.3 would see.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path


def main() -> int:
    import chromadb

    version = chromadb.__version__

    tmpdir = tempfile.mkdtemp(prefix=f"type-xver-{version}-")
    palace_dir = Path(tmpdir) / "test-palace"

    print(f"[INFO] ChromaDB version: {version}")
    print(f"[INFO] Palace dir: {palace_dir}")

    # Create a palace
    client = chromadb.PersistentClient(path=str(palace_dir))
    col = client.get_or_create_collection("mempalace_drawers", metadata={"hnsw:space": "cosine"})
    col.add(
        ids=["test-1"],
        documents=["This is a test drawer."],
        metadatas=[{"wing": "test", "room": "general"}],
    )
    del client

    # Read raw config_json_str
    db_path = palace_dir / "chroma.sqlite3"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Check schema
    cur.execute("PRAGMA table_info(collections)")
    cols = cur.fetchall()
    print(f"\n[INFO] collections table schema:")
    for c in cols:
        print(f"  {c[1]} ({c[2]})")

    cur.execute("SELECT id, name, config_json_str FROM collections")
    rows = cur.fetchall()
    for row in rows:
        col_id, col_name, config_str = row
        print(f"\n[INFO] Collection: {col_name}")
        print(f"[INFO] Raw config_json_str: {config_str}")
        config = json.loads(config_str or "{}")
        print(f"[INFO] Keys: {list(config.keys())}")
        print(f"[INFO] '_type' present: {'_type' in config}")
        if "_type" in config:
            print(f"[INFO] '_type' value: {config['_type']}")
        print(f"[INFO] Pretty printed:")
        print(json.dumps(config, indent=2))

    conn.close()

    # Don't clean up - leave for manual inspection
    print(f"\n[INFO] Palace left at: {palace_dir}")
    print(f"[INFO] To inspect: sqlite3 {db_path} 'SELECT config_json_str FROM collections;'")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
