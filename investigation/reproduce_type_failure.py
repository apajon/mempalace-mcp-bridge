#!/usr/bin/env python3
"""
Minimal reproduction for the _type runtime failure.

Creates a temporary palace with a collection whose config_json_str lacks _type,
then attempts to load it the way mempalace MCP runtime would.

This simulates what happens when a reconstructed palace (created under a different
chromadb version) is opened by chromadb 0.6.x runtime.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import traceback
from pathlib import Path


def create_minimal_palace_with_missing_type(palace_dir: Path) -> None:
    """Create a palace via chromadb API, then corrupt config_json_str to simulate the issue."""
    import chromadb

    # Step 1: Create a valid palace with a collection
    client = chromadb.PersistentClient(path=str(palace_dir))
    col = client.get_or_create_collection("mempalace_drawers", metadata={"hnsw:space": "cosine"})
    col.add(
        ids=["test-1"],
        documents=["This is a test drawer for reproduction."],
        metadatas=[{"wing": "test", "room": "general"}],
    )
    del client  # Release the client

    # Step 2: Read the current config_json_str to show what's expected
    db_path = palace_dir / "chroma.sqlite3"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT id, name, config_json_str FROM collections")
    rows = cur.fetchall()
    print(f"[INFO] Collections before corruption:")
    for row in rows:
        print(f"  id={row[0]}, name={row[1]}")
        config = json.loads(row[2] or "{}")
        print(f"  config_json_str keys: {list(config.keys())}")
        print(f"  _type present: {'_type' in config}")
        print(f"  _type value: {config.get('_type', '<MISSING>')}")
    print()

    # Step 3: Corrupt config_json_str by removing _type (simulates a palace
    # created by a runtime that doesn't write _type)
    for row in rows:
        cur.execute(
            "UPDATE collections SET config_json_str = ? WHERE id = ?",
            ("{}", row[0]),
        )
    conn.commit()
    conn.close()

    print("[INFO] Corrupted config_json_str to '{}' (simulates missing _type)")
    print()


def attempt_load_via_chromadb(palace_dir: Path) -> None:
    """Attempt to load the palace the way mempalace runtime does."""
    import chromadb

    print("=" * 60)
    print("PHASE 1: Direct chromadb.PersistentClient.get_collection()")
    print("=" * 60)
    try:
        client = chromadb.PersistentClient(path=str(palace_dir))
        col = client.get_collection("mempalace_drawers")
        print(f"[OK] Collection loaded: {col.name}, count={col.count()}")
    except Exception as exc:
        print(f"[FAIL] Exception type: {type(exc).__module__}.{type(exc).__qualname__}")
        print(f"[FAIL] Exception message: {exc}")
        print(f"[FAIL] Full traceback:")
        traceback.print_exc()
    print()


def attempt_load_via_mempalace_pattern(palace_dir: Path) -> None:
    """Simulate mempalace's _get_collection() which catches all exceptions."""
    import chromadb

    print("=" * 60)
    print("PHASE 2: Simulated mempalace _get_collection() pattern")
    print("=" * 60)

    # This is exactly what mempalace does:
    try:
        client = chromadb.PersistentClient(path=str(palace_dir))
        collection = client.get_collection("mempalace_drawers")
        print(f"[OK] Collection loaded: {collection.name}")
    except Exception:
        collection = None

    if collection is None:
        print("[FAIL] _get_collection() returned None → user sees 'No palace found'")
        print("[INFO] The real exception was silently swallowed by 'except Exception'")
    print()


def attempt_load_with_instrumentation(palace_dir: Path) -> None:
    """Load with full instrumentation to expose the exact failure."""
    import chromadb

    print("=" * 60)
    print("PHASE 3: Instrumented load — exposing the real failure")
    print("=" * 60)

    # Read the raw SQLite data first
    db_path = palace_dir / "chroma.sqlite3"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT id, name, config_json_str FROM collections")
    rows = cur.fetchall()
    conn.close()

    for row in rows:
        col_id, col_name, config_json_str = row
        print(f"[INFO] Collection: {col_name} (id={col_id})")
        print(f"[INFO] Raw config_json_str: {repr(config_json_str)}")
        config = json.loads(config_json_str or "{}")
        print(f"[INFO] Parsed config type: {type(config).__name__}")
        print(f"[INFO] Parsed config keys: {list(config.keys())}")
        print(f"[INFO] '_type' key present: {'_type' in config}")
        print(f"[INFO] '_type' value: {config.get('_type', '<MISSING>')}")
        print(f"[INFO] bool(config): {bool(config)}")
        print()

        # Now trace exactly through the from_json_str path
        from chromadb.api.configuration import CollectionConfigurationInternal

        print("[INFO] Calling CollectionConfigurationInternal.from_json_str(config_json_str)...")
        try:
            result = CollectionConfigurationInternal.from_json_str(config_json_str)
            print(f"[OK] Deserialized successfully: {result}")
        except KeyError as ke:
            print(f"[FAIL] KeyError: {ke}")
            print(f"[INFO] This is the actual bug: the error message at line 209 of")
            print(f"       chromadb/api/configuration.py tries to access json_map['_type']")
            print(f"       but '_type' is not in the dict, so KeyError is raised")
            print(f"       INSTEAD of the intended ValueError.")
            traceback.print_exc()
        except ValueError as ve:
            print(f"[FAIL] ValueError: {ve}")
            traceback.print_exc()
        except Exception as exc:
            print(f"[FAIL] Unexpected {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print()


def main() -> int:
    tmpdir = tempfile.mkdtemp(prefix="mempalace-type-repro-")
    palace_dir = Path(tmpdir) / "test-palace"

    try:
        print(f"[INFO] Temp palace directory: {palace_dir}")
        print()

        create_minimal_palace_with_missing_type(palace_dir)
        attempt_load_via_chromadb(palace_dir)
        attempt_load_via_mempalace_pattern(palace_dir)
        attempt_load_with_instrumentation(palace_dir)

        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print("When config_json_str lacks '_type', the following occurs:")
        print("1. CollectionConfigurationInternal.from_json() checks:")
        print("     cls.__name__ != json_map.get('_type', None)")
        print("   → 'CollectionConfigurationInternal' != None → True")
        print("2. It then formats an error message with json_map['_type']")
        print("   → KeyError: '_type' (because the key doesn't exist)")
        print("3. mempalace's _get_collection() catches all exceptions → None")
        print("4. User sees: {'error': 'No palace found'}")
        print()
        print("Root cause: chromadb/api/configuration.py line ~209")
        print("  raise ValueError(f\"...{json_map['_type']}\")")
        print("  uses dict access instead of .get() in the error message")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
