#!/usr/bin/env python3
"""
Runtime compatibility test harness.

Tests whether a given palace can be loaded, queried, and served by MCP
in a given Python/ChromaDB/MemPalace environment.

Usage:
    <python-from-target-venv> runtime_load_test.py <palace_dir> [--mcp]

Phases:
  1. Version fingerprint
  2. Raw SQLite config inspection
  3. ChromaDB client load
  4. Collection access
  5. Query execution
  6. (optional) MCP server tool registration

Exit codes:
  0 = all tested phases passed
  1 = at least one phase failed
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import traceback
from pathlib import Path


def phase(name: str):
    """Decorator to run a phase and capture success/failure."""
    def decorator(fn):
        fn._phase_name = name
        return fn
    return decorator


class RuntimeLoadTest:
    def __init__(self, palace_dir: str, test_mcp: bool = False):
        self.palace_dir = Path(palace_dir)
        self.test_mcp = test_mcp
        self.results: list[dict] = []

    def _record(self, phase: str, passed: bool, detail: str, exc: str = ""):
        self.results.append({
            "phase": phase,
            "passed": passed,
            "detail": detail,
            "exception": exc,
        })
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {phase}: {detail}")
        if exc:
            print(f"       exception: {exc}")

    def run_all(self) -> int:
        self.phase_versions()
        self.phase_raw_config()
        self.phase_client_load()
        self.phase_collection_access()
        self.phase_query()
        if self.test_mcp:
            self.phase_mcp_tools()

        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        all_pass = True
        for r in self.results:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"  [{status}] {r['phase']}")
            if not r["passed"]:
                all_pass = False

        print(f"\nOverall: {'ALL PASSED' if all_pass else 'FAILURES DETECTED'}")
        return 0 if all_pass else 1

    def phase_versions(self):
        """Phase 1: version fingerprint."""
        try:
            import chromadb
            cv = chromadb.__version__
        except Exception as e:
            self._record("1_versions", False, "chromadb not importable", str(e))
            return

        try:
            import mempalace
            mv = mempalace.__version__
        except Exception:
            mv = "not installed"

        self._record("1_versions", True, f"python={sys.version.split()[0]} chromadb={cv} mempalace={mv}")

    def phase_raw_config(self):
        """Phase 2: raw SQLite config inspection."""
        db = self.palace_dir / "chroma.sqlite3"
        if not db.exists():
            self._record("2_raw_config", False, f"No chroma.sqlite3 at {db}")
            return

        try:
            conn = sqlite3.connect(str(db))
            cur = conn.cursor()

            # Schema
            cur.execute("PRAGMA table_info(collections)")
            columns = [row[1] for row in cur.fetchall()]

            cur.execute("SELECT name, config_json_str FROM collections")
            rows = cur.fetchall()
            conn.close()

            for name, cfg in rows:
                config = json.loads(cfg or "{}")
                has_type = "_type" in config
                self._record(
                    "2_raw_config",
                    True,
                    f"collection={name} columns={columns} "
                    f"config_keys={list(config.keys())} "
                    f"has_type={has_type} "
                    f"raw={cfg!r}"
                )
        except Exception as e:
            self._record("2_raw_config", False, "SQLite read failed", traceback.format_exc())

    def phase_client_load(self):
        """Phase 3: ChromaDB PersistentClient instantiation."""
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=str(self.palace_dir))
            self._record("3_client_load", True, "PersistentClient created")
        except Exception as e:
            self._client = None
            self._record("3_client_load", False, "PersistentClient failed", traceback.format_exc())

    def phase_collection_access(self):
        """Phase 4: get_collection('mempalace_drawers')."""
        if self._client is None:
            self._record("4_collection_access", False, "Skipped: no client")
            return

        try:
            self._collection = self._client.get_collection("mempalace_drawers")
            count = self._collection.count()
            self._record("4_collection_access", True, f"Collection loaded, count={count}")
        except Exception as e:
            self._collection = None
            self._record("4_collection_access", False, "get_collection failed", traceback.format_exc())

    def phase_query(self):
        """Phase 5: query execution."""
        if not hasattr(self, '_collection') or self._collection is None:
            self._record("5_query", False, "Skipped: no collection")
            return

        try:
            results = self._collection.query(
                query_texts=["dependency management"],
                n_results=2,
            )
            ids = results.get("ids", [[]])[0] if results else []
            self._record("5_query", True, f"Query returned {len(ids)} results: {ids}")
        except Exception as e:
            self._record("5_query", False, "Query failed", traceback.format_exc())

    def phase_mcp_tools(self):
        """Phase 6: MCP tool registration (import-level check)."""
        try:
            # Set palace path for mempalace config
            os.environ["MEMPALACE_PALACE_PATH"] = str(self.palace_dir)

            from mempalace.mcp_server import mcp  # noqa: F401

            # Check if tools are registered
            # The mcp object should have tool registrations
            self._record("6_mcp_tools", True, "MCP server module imported, mcp object available")
        except Exception as e:
            self._record("6_mcp_tools", False, "MCP import failed", traceback.format_exc())

    def to_log(self) -> str:
        """Return full log as string."""
        lines = []
        lines.append(f"Palace: {self.palace_dir}")
        lines.append(f"Python: {sys.executable}")
        lines.append("")
        for r in self.results:
            status = "PASS" if r["passed"] else "FAIL"
            lines.append(f"[{status}] {r['phase']}: {r['detail']}")
            if r["exception"]:
                lines.append(f"  Exception:\n{r['exception']}")
        return "\n".join(lines)


def main() -> int:
    args = sys.argv[1:]
    test_mcp = "--mcp" in args
    args = [a for a in args if a != "--mcp"]

    if not args:
        print(f"Usage: {sys.argv[0]} <palace_dir> [--mcp]", file=sys.stderr)
        return 1

    palace_dir = args[0]
    test = RuntimeLoadTest(palace_dir, test_mcp=test_mcp)
    return test.run_all()


if __name__ == "__main__":
    raise SystemExit(main())
