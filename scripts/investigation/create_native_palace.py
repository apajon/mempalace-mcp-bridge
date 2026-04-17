#!/usr/bin/env python3
"""
Create a native palace in the current ChromaDB environment.

Usage:
    <python-from-target-venv> create_native_palace.py <palace_dir>

Creates a minimal but representative palace with known content,
then verifies it can be loaded back in the same runtime.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <palace_dir>", file=sys.stderr)
        return 1

    palace_dir = Path(sys.argv[1])

    import chromadb

    version = chromadb.__version__
    try:
        import mempalace

        mp_version = mempalace.__version__
    except Exception:
        mp_version = "unavailable"

    print(f"[create] chromadb={version} mempalace={mp_version}")
    print(f"[create] target: {palace_dir}")

    if palace_dir.exists():
        print(f"[create] ERROR: {palace_dir} already exists", file=sys.stderr)
        return 1

    palace_dir.mkdir(parents=True)

    # Create palace via ChromaDB API
    client = chromadb.PersistentClient(path=str(palace_dir))
    col = client.get_or_create_collection(
        "mempalace_drawers", metadata={"hnsw:space": "cosine"}
    )

    # Add representative drawers
    drawers = [
        {
            "id": "test-arch-001",
            "document": "The MCP bridge uses stdio transport for VS Code integration.",
            "metadata": {
                "wing": "test_project",
                "room": "architecture",
                "source": "native_test",
            },
        },
        {
            "id": "test-conv-001",
            "document": "Always use uv for dependency management, never raw pip.",
            "metadata": {
                "wing": "test_project",
                "room": "conventions",
                "source": "native_test",
            },
        },
        {
            "id": "test-debug-001",
            "document": "ChromaDB telemetry errors are harmless noise in dev environments.",
            "metadata": {
                "wing": "test_project",
                "room": "debugging",
                "source": "native_test",
            },
        },
    ]

    col.add(
        ids=[d["id"] for d in drawers],
        documents=[d["document"] for d in drawers],
        metadatas=[d["metadata"] for d in drawers],
    )

    print(f"[create] Added {len(drawers)} drawers")

    # Verify roundtrip
    del client
    client2 = chromadb.PersistentClient(path=str(palace_dir))
    try:
        col2 = client2.get_collection("mempalace_drawers")
        count = col2.count()
        print(f"[create] Roundtrip verify: collection loaded, count={count}")
    except Exception as e:
        print(f"[create] Roundtrip verify FAILED: {e}", file=sys.stderr)
        return 1

    # Dump raw config_json_str for inspection
    db_path = palace_dir / "chroma.sqlite3"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT name, config_json_str FROM collections")
    for name, cfg in cur.fetchall():
        print(f"[create] config_json_str({name}): {cfg}")
    conn.close()

    # Query test
    results = col2.query(query_texts=["dependency management"], n_results=1)
    if results and results["ids"] and results["ids"][0]:
        print(f"[create] Query test: returned id={results['ids'][0][0]}")
    else:
        print("[create] Query test: no results")

    print(f"[create] SUCCESS: native palace at {palace_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
