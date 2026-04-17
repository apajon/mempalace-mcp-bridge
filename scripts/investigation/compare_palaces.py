#!/usr/bin/env python3
"""Migration-grade comparison: native 1.x vs reconstructed 1.x palace.

Validates structural parity, retrieval parity, and metadata fidelity across
the two palaces.  Both palaces MUST be loaded via the same runtime.

Usage:
    <python> compare_palaces.py <palace_a_path> <palace_b_path> [--label-a NAME] [--label-b NAME]

Exit codes:
    0  — all checks passed
    1  — at least one check failed
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def _load_all(palace_path: Path) -> dict:
    """Load all drawers via ChromaDB API."""
    import chromadb

    client = chromadb.PersistentClient(path=str(palace_path))
    col = client.get_collection("mempalace_drawers")
    count = col.count()

    # get() with no filter returns all
    data = col.get(include=["documents", "metadatas", "embeddings"])
    return {
        "count": count,
        "ids": data["ids"],
        "documents": data["documents"],
        "metadatas": data["metadatas"],
        "embeddings": data["embeddings"],
    }


def _raw_config(palace_path: Path) -> dict[str, str]:
    """Read raw config_json_str per collection from SQLite."""
    db = palace_path / "chroma.sqlite3"
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    cur.execute("SELECT name, config_json_str FROM collections")
    result = {name: config for name, config in cur.fetchall()}
    conn.close()
    return result


def _run_queries(palace_path: Path, queries: list[str], n_results: int = 5) -> dict[str, list[str]]:
    """Run queries and return {query: [top_ids]}."""
    import chromadb

    client = chromadb.PersistentClient(path=str(palace_path))
    col = client.get_collection("mempalace_drawers")
    results = {}
    for q in queries:
        r = col.query(query_texts=[q], n_results=n_results)
        results[q] = r["ids"][0]
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two palaces for migration-grade parity.")
    parser.add_argument("palace_a", help="Path to first palace")
    parser.add_argument("palace_b", help="Path to second palace")
    parser.add_argument("--label-a", default="A", help="Label for palace A")
    parser.add_argument("--label-b", default="B", help="Label for palace B")
    args = parser.parse_args()

    path_a = Path(args.palace_a).expanduser().resolve()
    path_b = Path(args.palace_b).expanduser().resolve()
    label_a = args.label_a
    label_b = args.label_b

    import chromadb
    print(f"[compare] chromadb={chromadb.__version__}")
    print(f"[compare] {label_a}: {path_a}")
    print(f"[compare] {label_b}: {path_b}")
    print()

    failures = []

    # -----------------------------------------------------------------------
    # Tier 1: Storage reconstruction validity
    # -----------------------------------------------------------------------
    print("=" * 60)
    print("TIER 1: Storage reconstruction validity")
    print("=" * 60)

    config_a = _raw_config(path_a)
    config_b = _raw_config(path_b)

    if set(config_a.keys()) == set(config_b.keys()):
        print(f"[PASS] Collection names match: {sorted(config_a.keys())}")
    else:
        msg = f"Collection names differ: {label_a}={sorted(config_a.keys())} {label_b}={sorted(config_b.keys())}"
        print(f"[FAIL] {msg}")
        failures.append(msg)

    for col_name in config_a:
        if col_name in config_b:
            ca = json.loads(config_a[col_name] or "{}")
            cb = json.loads(config_b[col_name] or "{}")
            # Compare structure (keys), not exact values — embeddings may differ
            if set(ca.keys()) == set(cb.keys()):
                print(f"[PASS] Collection '{col_name}' config keys match: {sorted(ca.keys())}")
            else:
                msg = f"Collection '{col_name}' config keys differ: {label_a}={sorted(ca.keys())} {label_b}={sorted(cb.keys())}"
                print(f"[FAIL] {msg}")
                failures.append(msg)

    # -----------------------------------------------------------------------
    # Tier 2: Structural parity
    # -----------------------------------------------------------------------
    print()
    print("=" * 60)
    print("TIER 2: Structural parity")
    print("=" * 60)

    data_a = _load_all(path_a)
    data_b = _load_all(path_b)

    if data_a["count"] == data_b["count"]:
        print(f"[PASS] Drawer count matches: {data_a['count']}")
    else:
        msg = f"Drawer count differs: {label_a}={data_a['count']} {label_b}={data_b['count']}"
        print(f"[FAIL] {msg}")
        failures.append(msg)

    ids_a = set(data_a["ids"])
    ids_b = set(data_b["ids"])
    if ids_a == ids_b:
        print(f"[PASS] All {len(ids_a)} drawer IDs match")
    else:
        only_a = ids_a - ids_b
        only_b = ids_b - ids_a
        msg = f"ID sets differ: only_in_{label_a}={only_a} only_in_{label_b}={only_b}"
        print(f"[FAIL] {msg}")
        failures.append(msg)

    # Build lookup dicts
    lookup_a = {data_a["ids"][i]: i for i in range(len(data_a["ids"]))}
    lookup_b = {data_b["ids"][i]: i for i in range(len(data_b["ids"]))}

    # -----------------------------------------------------------------------
    # Tier 3: Document content parity
    # -----------------------------------------------------------------------
    print()
    print("=" * 60)
    print("TIER 3: Document content parity")
    print("=" * 60)

    doc_mismatches = 0
    for drawer_id in sorted(ids_a & ids_b):
        doc_a = data_a["documents"][lookup_a[drawer_id]]
        doc_b = data_b["documents"][lookup_b[drawer_id]]
        if doc_a != doc_b:
            doc_mismatches += 1
            if doc_mismatches <= 5:  # cap output
                print(f"[FAIL] Document mismatch for '{drawer_id}':")
                print(f"       {label_a}: {doc_a[:100]!r}...")
                print(f"       {label_b}: {doc_b[:100]!r}...")

    if doc_mismatches == 0:
        print(f"[PASS] All {len(ids_a & ids_b)} documents are identical")
    else:
        msg = f"{doc_mismatches} document(s) differ"
        failures.append(msg)

    # -----------------------------------------------------------------------
    # Tier 4: Metadata parity
    # -----------------------------------------------------------------------
    print()
    print("=" * 60)
    print("TIER 4: Metadata parity")
    print("=" * 60)

    meta_mismatches = 0
    for drawer_id in sorted(ids_a & ids_b):
        meta_a = data_a["metadatas"][lookup_a[drawer_id]]
        meta_b = data_b["metadatas"][lookup_b[drawer_id]]
        if meta_a != meta_b:
            meta_mismatches += 1
            if meta_mismatches <= 5:
                print(f"[FAIL] Metadata mismatch for '{drawer_id}':")
                print(f"       {label_a}: {meta_a}")
                print(f"       {label_b}: {meta_b}")

    if meta_mismatches == 0:
        print(f"[PASS] All {len(ids_a & ids_b)} metadata records are identical")
    else:
        msg = f"{meta_mismatches} metadata record(s) differ"
        failures.append(msg)

    # -----------------------------------------------------------------------
    # Tier 5: Embedding parity
    # -----------------------------------------------------------------------
    print()
    print("=" * 60)
    print("TIER 5: Embedding parity")
    print("=" * 60)

    emb_mismatches = 0
    emb_total = 0
    max_diff = 0.0
    for drawer_id in sorted(ids_a & ids_b):
        emb_a = data_a["embeddings"][lookup_a[drawer_id]]
        emb_b = data_b["embeddings"][lookup_b[drawer_id]]
        if emb_a is None or emb_b is None:
            continue
        emb_total += 1
        if len(emb_a) != len(emb_b):
            emb_mismatches += 1
            continue
        diff = max(abs(a - b) for a, b in zip(emb_a, emb_b))
        max_diff = max(max_diff, diff)
        if diff > 1e-6:
            emb_mismatches += 1

    if emb_total == 0:
        print("[SKIP] No embeddings available for comparison")
    elif emb_mismatches == 0:
        print(f"[PASS] All {emb_total} embeddings match (max_diff={max_diff:.2e})")
    else:
        msg = f"{emb_mismatches}/{emb_total} embeddings differ (max_diff={max_diff:.2e})"
        print(f"[FAIL] {msg}")
        failures.append(msg)

    # -----------------------------------------------------------------------
    # Tier 6: Retrieval parity (query results)
    # -----------------------------------------------------------------------
    print()
    print("=" * 60)
    print("TIER 6: Retrieval parity")
    print("=" * 60)

    test_queries = [
        "database connection pooling",
        "ROS 2 navigation behavior tree",
        "Python type hints and dataclasses",
        "Docker multi-stage build",
        "emoji preservation in documents",
        "virtual environment dependency management",
        "authentication OIDC JWT",
        "Git commit message conventions",
    ]

    query_results_a = _run_queries(path_a, test_queries, n_results=5)
    query_results_b = _run_queries(path_b, test_queries, n_results=5)

    query_mismatches = 0
    for q in test_queries:
        ids_qa = query_results_a[q]
        ids_qb = query_results_b[q]
        if ids_qa == ids_qb:
            print(f"[PASS] Query '{q}': identical top-5 in order")
        elif set(ids_qa) == set(ids_qb):
            print(f"[WARN] Query '{q}': same IDs, different order")
            print(f"       {label_a}: {ids_qa}")
            print(f"       {label_b}: {ids_qb}")
        else:
            query_mismatches += 1
            print(f"[FAIL] Query '{q}': different results")
            print(f"       {label_a}: {ids_qa}")
            print(f"       {label_b}: {ids_qb}")

    if query_mismatches > 0:
        failures.append(f"{query_mismatches} query result(s) differ")

    # -----------------------------------------------------------------------
    # Wing/room diversity check
    # -----------------------------------------------------------------------
    print()
    print("=" * 60)
    print("DIVERSITY CHECK")
    print("=" * 60)

    wings_a = set(m.get("wing", "") for m in data_a["metadatas"])
    wings_b = set(m.get("wing", "") for m in data_b["metadatas"])
    rooms_a = set(f"{m.get('wing','')}/{m.get('room','')}" for m in data_a["metadatas"])
    rooms_b = set(f"{m.get('wing','')}/{m.get('room','')}" for m in data_b["metadatas"])

    print(f"[INFO] {label_a}: {len(wings_a)} wings, {len(rooms_a)} rooms")
    print(f"[INFO] {label_b}: {len(wings_b)} wings, {len(rooms_b)} rooms")
    if wings_a == wings_b and rooms_a == rooms_b:
        print("[PASS] Wing/room sets are identical")
    else:
        print(f"[FAIL] Wing/room sets differ")
        failures.append("Wing/room diversity mismatch")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if not failures:
        print(f"ALL CHECKS PASSED — {label_a} and {label_b} are migration-grade equivalent")
        return 0
    else:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
