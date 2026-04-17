from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from palace_reconstruction_prototype import (  # type: ignore
    DRAWERS_FILENAME,
    EXPORT_MANIFEST_FILENAME,
    MCP_RUNTIME_DEBUG_FILENAME,
    RETRIEVAL_QUERIES_FILENAME,
    RETRIEVAL_DEBUG_FILENAME,
    TARGET_MANIFEST_FILENAME,
    USAGE_SCENARIOS_FILENAME,
    USAGE_DEBUG_FILENAME,
    VALIDATION_DEBUG_FILENAME,
    COLLECTION_NAME,
    compare_usage_results,
    compare_retrieval_results,
    export_drawers,
    import_drawers,
    record_usage_results,
    record_retrieval_results,
    summarize_drawers,
    validate_mcp_runtime,
    validate_reconstruction,
)


class PalaceReconstructionPrototypeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_source_palace(self, rows: list[dict[str, object]] | None = None) -> Path:
        palace = self.root / "source-palace"
        palace.mkdir(parents=True, exist_ok=True)

        manifest = {
            "compatibility_line": "chromadb-0.6.x",
            "chromadb_version": "0.6.3",
        }
        (palace / "mempalace-bridge-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
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

        if rows is None:
            rows = [
                {
                    "row_id": 1,
                    "id": "drawer_a",
                    "document": "alpha text",
                    "metadata": {"wing": "proj", "room": "docs", "chunk_index": 0},
                },
                {
                    "row_id": 2,
                    "id": "drawer_b",
                    "document": "beta text",
                    "metadata": {"wing": "proj", "room": "code", "chunk_index": 1},
                },
            ]

        for row in rows:
            row_id = int(row["row_id"])
            embedding_id = row["id"]
            document_entries = row.get("document_entries", [row.get("document")])
            metadata = dict(row.get("metadata", {}))
            cur.execute("INSERT INTO embeddings (id, embedding_id) VALUES (?, ?)", (row_id, embedding_id))
            for document in document_entries:
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
                        (row_id, key, value),
                    )

        conn.commit()
        conn.close()
        return palace

    def _open_target_collection(self, target: Path):
        import chromadb

        client = chromadb.PersistentClient(path=str(target))
        return client.get_collection(COLLECTION_NAME)

    def _write_queryable_palace(
        self,
        rows: list[dict[str, object]] | None = None,
        *,
        name: str = "queryable-palace",
    ) -> Path:
        import chromadb

        palace = self.root / name
        palace.mkdir(parents=True, exist_ok=True)
        manifest = {
            "compatibility_line": "chromadb-0.6.x",
            "chromadb_version": "0.6.3",
        }
        (palace / "mempalace-bridge-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        if rows is None:
            rows = [
                {
                    "id": "drawer_alpha",
                    "document": "alpha planning notes for migration validation",
                    "metadata": {"wing": "proj", "room": "docs", "chunk_index": 0},
                },
                {
                    "id": "drawer_beta",
                    "document": "beta implementation details for reconstruction",
                    "metadata": {"wing": "proj", "room": "code", "chunk_index": 1},
                },
                {
                    "id": "drawer_gamma",
                    "document": "gamma troubleshooting guide for mempalace queries",
                    "metadata": {"wing": "shared", "room": "notes", "chunk_index": 2},
                },
            ]

        client = chromadb.PersistentClient(path=str(palace))
        collection = client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
        collection.add(
            ids=[str(row["id"]) for row in rows],
            documents=[str(row["document"]) for row in rows],
            metadatas=[dict(row["metadata"]) for row in rows],
        )
        return palace

    def _run_reconstruct_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPTS_DIR / "reconstruct.sh"), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def _run_prototype_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(REPO_ROOT / ".venv/bin/python"), str(SCRIPTS_DIR / "palace_reconstruction_prototype.py"), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_summarize_drawers_counts_wings_and_rooms(self) -> None:
        summary = summarize_drawers(
            [
                {"id": "a", "document": "one", "metadata": {"wing": "proj", "room": "docs"}},
                {"id": "b", "document": "two", "metadata": {"wing": "proj", "room": "docs"}},
                {"id": "c", "document": "three", "metadata": {"wing": "proj", "room": "code"}},
            ]
        )

        self.assertEqual(summary["drawer_count"], 3)
        self.assertEqual(summary["wing_room_counts"]["proj"]["docs"], 2)
        self.assertEqual(summary["wing_room_counts"]["proj"]["code"], 1)
        self.assertEqual(summary["id_integrity"]["duplicate_id_count"], 0)
        self.assertEqual(summary["content_integrity"]["empty_document_count"], 0)
        self.assertEqual(summary["content_integrity"]["length_profile"]["total_chars"], 11)

    def test_export_import_validate_roundtrip(self) -> None:
        source = self._write_source_palace()
        export_dir = self.root / "export"
        target = self.root / "target"

        export_manifest = export_drawers(source, export_dir)
        self.assertTrue((export_dir / EXPORT_MANIFEST_FILENAME).exists())
        self.assertTrue((export_dir / DRAWERS_FILENAME).exists())
        self.assertTrue((export_dir / RETRIEVAL_QUERIES_FILENAME).exists())
        self.assertTrue((export_dir / USAGE_SCENARIOS_FILENAME).exists())
        self.assertEqual(export_manifest["summary"]["drawer_count"], 2)
        self.assertEqual(export_manifest["bundle_type"], "mempalace_reconstruction_bundle")
        self.assertEqual(export_manifest["files"]["drawers"], DRAWERS_FILENAME)
        self.assertEqual(export_manifest["files"]["retrieval_queries"], RETRIEVAL_QUERIES_FILENAME)
        self.assertEqual(export_manifest["files"]["usage_scenarios"], USAGE_SCENARIOS_FILENAME)
        self.assertEqual(export_manifest["collection"]["name"], COLLECTION_NAME)
        self.assertGreaterEqual(export_manifest["usage_validation"]["scenario_count"], 3)

        target_manifest = import_drawers(export_dir, target)
        self.assertTrue((target / TARGET_MANIFEST_FILENAME).exists())
        self.assertEqual(target_manifest["target"]["imported_drawer_count"], 2)

        validation = validate_reconstruction(export_dir, target)
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["actual_drawer_count"], 2)
        self.assertTrue(validation["checks"]["id_sets_match"])
        self.assertTrue(validation["checks"]["content_hashes_match"])
        self.assertTrue(validation["checks"]["metadata_values_match"])
        self.assertEqual(validation["diagnostics"]["ids"]["missing_in_target"], [])
        self.assertEqual(validation["diagnostics"]["content"]["mismatched_ids"], [])
        self.assertEqual(validation["diagnostics"]["metadata"]["mismatched_ids"], [])
        self.assertIn("embeddings", validation["diagnostics"])

    def test_export_rejects_duplicate_source_ids(self) -> None:
        source = self._write_source_palace(
            [
                {
                    "row_id": 1,
                    "id": "drawer_a",
                    "document": "alpha text",
                    "metadata": {"wing": "proj", "room": "docs"},
                },
                {
                    "row_id": 2,
                    "id": "drawer_a",
                    "document": "beta text",
                    "metadata": {"wing": "proj", "room": "code"},
                },
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "duplicate source ids"):
            export_drawers(source, self.root / "export")

    def test_export_rejects_empty_documents(self) -> None:
        source = self._write_source_palace(
            [
                {
                    "row_id": 1,
                    "id": "drawer_a",
                    "document": "   ",
                    "metadata": {"wing": "proj", "room": "docs"},
                }
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "empty exported documents"):
            export_drawers(source, self.root / "export")

    def test_import_accepts_legacy_manifest_without_explicit_bundle_fields(self) -> None:
        source = self._write_source_palace()
        export_dir = self.root / "export"
        target = self.root / "target"

        export_drawers(source, export_dir)
        manifest_path = export_dir / EXPORT_MANIFEST_FILENAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        del manifest["bundle_type"]
        del manifest["files"]
        del manifest["collection"]
        del manifest["retrieval_validation"]
        del manifest["usage_validation"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        target_manifest = import_drawers(export_dir, target)
        self.assertEqual(target_manifest["target"]["imported_drawer_count"], 2)

    def test_import_rejects_manifest_missing_required_summary_fields(self) -> None:
        source = self._write_source_palace()
        export_dir = self.root / "export"

        export_drawers(source, export_dir)
        manifest_path = export_dir / EXPORT_MANIFEST_FILENAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        del manifest["summary"]["drawer_count"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "summary.drawer_count"):
            import_drawers(export_dir, self.root / "target")

    def test_validate_detects_id_content_and_metadata_drift(self) -> None:
        source = self._write_source_palace()
        export_dir = self.root / "export"
        target = self.root / "target"

        export_drawers(source, export_dir)
        import_drawers(export_dir, target)

        collection = self._open_target_collection(target)
        collection.delete(ids=["drawer_a", "drawer_b"])
        collection.add(
            ids=["drawer_a"],
            documents=["alpha text changed"],
            metadatas=[{"wing": "proj", "chunk_index": 0}],
        )
        collection.upsert(
            ids=["drawer_extra"],
            documents=["unexpected text"],
            metadatas=[{"wing": "proj", "room": "misc", "chunk_index": 9}],
        )

        validation = validate_reconstruction(export_dir, target)

        self.assertFalse(validation["valid"])
        self.assertFalse(validation["checks"]["id_sets_match"])
        self.assertFalse(validation["checks"]["content_hashes_match"])
        self.assertFalse(validation["checks"]["metadata_keys_preserved"])
        self.assertFalse(validation["checks"]["metadata_values_match"])
        self.assertEqual(validation["diagnostics"]["ids"]["missing_in_target"], ["drawer_b"])
        self.assertEqual(validation["diagnostics"]["ids"]["unexpected_in_target"], ["drawer_extra"])
        self.assertEqual(validation["diagnostics"]["content"]["mismatched_ids"], ["drawer_a"])
        self.assertEqual(validation["diagnostics"]["metadata"]["mismatched_ids"], ["drawer_a"])
        self.assertEqual(
            validation["diagnostics"]["metadata"]["missing_keys_in_target"],
            {"drawer_a": ["room"]},
        )

    def test_record_and_compare_retrieval_roundtrip(self) -> None:
        source = self._write_queryable_palace(name="source-palace")
        export_dir = self.root / "export"
        target = self.root / "target"
        source_results = self.root / "source-retrieval.json"
        target_results = self.root / "target-retrieval.json"

        export_drawers(source, export_dir)
        import_drawers(export_dir, target)

        source_record = record_retrieval_results(
            source,
            export_dir / RETRIEVAL_QUERIES_FILENAME,
            source_results,
            label="source",
        )
        target_record = record_retrieval_results(
            target,
            export_dir / RETRIEVAL_QUERIES_FILENAME,
            target_results,
            label="target",
        )
        comparison = compare_retrieval_results(source_results, target_results)

        self.assertEqual(source_record["query_count"], target_record["query_count"])
        self.assertTrue(comparison["valid"])
        self.assertTrue(comparison["checks"]["query_plan_matches"])
        self.assertTrue(comparison["checks"]["target_anchor_ids_present"])
        self.assertTrue(comparison["checks"]["id_overlap_meets_threshold"])

    def test_compare_retrieval_detects_semantic_drift(self) -> None:
        source = self._write_queryable_palace(name="source-palace")
        export_dir = self.root / "export"
        target = self.root / "target"
        source_results = self.root / "source-retrieval.json"
        target_results = self.root / "target-retrieval.json"

        export_drawers(source, export_dir)
        import_drawers(export_dir, target)

        collection = self._open_target_collection(target)
        collection.delete(ids=["drawer_alpha", "drawer_beta", "drawer_gamma"])
        collection.add(
            ids=["drawer_delta", "drawer_epsilon", "drawer_zeta"],
            documents=[
                "delta unrelated content about another topic",
                "epsilon unrelated content about another topic",
                "zeta unrelated content about another topic",
            ],
            metadatas=[
                {"wing": "other", "room": "misc", "chunk_index": 10},
                {"wing": "other", "room": "misc", "chunk_index": 11},
                {"wing": "other", "room": "misc", "chunk_index": 12},
            ],
        )

        record_retrieval_results(
            source,
            export_dir / RETRIEVAL_QUERIES_FILENAME,
            source_results,
            label="source",
        )
        record_retrieval_results(
            target,
            export_dir / RETRIEVAL_QUERIES_FILENAME,
            target_results,
            label="target",
        )
        comparison = compare_retrieval_results(source_results, target_results)

        self.assertFalse(comparison["valid"])
        self.assertFalse(comparison["checks"]["target_anchor_ids_present"])
        self.assertFalse(comparison["checks"]["id_overlap_meets_threshold"])
        self.assertGreaterEqual(len(comparison["summary"]["mismatch_query_ids"]), 1)

    def test_validate_mcp_runtime_succeeds_against_reconstructed_target(self) -> None:
        source = self._write_queryable_palace(name="source-palace")
        export_dir = self.root / "export"
        target = self.root / "target"

        export_drawers(source, export_dir)
        import_drawers(export_dir, target)

        result = validate_mcp_runtime(
            export_dir,
            target,
            python_executable=REPO_ROOT / ".venv/bin/python",
            launcher_script=SCRIPTS_DIR / "run_mcp_server_exploration.py",
        )

        self.assertTrue(result["valid"])
        self.assertTrue(result["checks"]["server_started"])
        self.assertTrue(result["checks"]["required_tools_available"])
        self.assertTrue(result["checks"]["status_matches_drawer_count"])
        self.assertTrue(result["checks"]["taxonomy_matches_export"])
        self.assertTrue(result["checks"]["search_results_present"])
        self.assertTrue(result["checks"]["anchor_texts_present"])

    def test_validate_mcp_runtime_detects_runtime_query_mismatch(self) -> None:
        source = self._write_queryable_palace(name="source-palace")
        export_dir = self.root / "export"
        target = self.root / "target"

        export_drawers(source, export_dir)
        import_drawers(export_dir, target)

        collection = self._open_target_collection(target)
        collection.delete(ids=["drawer_alpha", "drawer_beta", "drawer_gamma"])
        collection.add(
            ids=["drawer_delta", "drawer_epsilon", "drawer_zeta"],
            documents=[
                "delta unrelated content about another topic",
                "epsilon unrelated content about another topic",
                "zeta unrelated content about another topic",
            ],
            metadatas=[
                {"wing": "other", "room": "misc", "chunk_index": 10},
                {"wing": "other", "room": "misc", "chunk_index": 11},
                {"wing": "other", "room": "misc", "chunk_index": 12},
            ],
        )

        result = validate_mcp_runtime(
            export_dir,
            target,
            python_executable=REPO_ROOT / ".venv/bin/python",
            launcher_script=SCRIPTS_DIR / "run_mcp_server_exploration.py",
        )

        self.assertFalse(result["valid"])
        self.assertFalse(result["checks"]["taxonomy_matches_export"])
        self.assertFalse(result["checks"]["anchor_texts_present"])
        self.assertTrue(any(query["mismatches"] for query in result["diagnostics"]["queries"]))

    def test_record_and_compare_usage_roundtrip(self) -> None:
        source = self._write_queryable_palace(name="source-palace")
        export_dir = self.root / "export"
        target = self.root / "target"
        source_results = self.root / "source-usage.json"
        target_results = self.root / "target-usage.json"

        export_drawers(source, export_dir)
        import_drawers(export_dir, target)

        source_record = record_usage_results(
            source,
            export_dir / USAGE_SCENARIOS_FILENAME,
            source_results,
            label="source",
        )
        target_record = record_usage_results(
            target,
            export_dir / USAGE_SCENARIOS_FILENAME,
            target_results,
            label="target",
        )
        comparison = compare_usage_results(source_results, target_results)

        self.assertEqual(source_record["scenario_count"], target_record["scenario_count"])
        self.assertTrue(comparison["valid"])
        self.assertEqual(comparison["recommendation"], "acceptable")
        self.assertTrue(comparison["checks"]["scenario_plan_matches"])
        self.assertTrue(comparison["checks"]["target_anchor_ids_present"])

    def test_compare_usage_detects_degraded_behavior(self) -> None:
        source = self._write_queryable_palace(name="source-palace")
        export_dir = self.root / "export"
        target = self.root / "target"
        source_results = self.root / "source-usage.json"
        target_results = self.root / "target-usage.json"

        export_drawers(source, export_dir)
        import_drawers(export_dir, target)

        collection = self._open_target_collection(target)
        collection.delete(ids=["drawer_alpha", "drawer_beta", "drawer_gamma"])
        collection.add(
            ids=["drawer_delta", "drawer_epsilon", "drawer_zeta"],
            documents=[
                "delta unrelated content about another topic",
                "epsilon unrelated content about another topic",
                "zeta unrelated content about another topic",
            ],
            metadatas=[
                {"wing": "other", "room": "misc", "chunk_index": 10},
                {"wing": "other", "room": "misc", "chunk_index": 11},
                {"wing": "other", "room": "misc", "chunk_index": 12},
            ],
        )

        record_usage_results(
            source,
            export_dir / USAGE_SCENARIOS_FILENAME,
            source_results,
            label="source",
        )
        record_usage_results(
            target,
            export_dir / USAGE_SCENARIOS_FILENAME,
            target_results,
            label="target",
        )
        comparison = compare_usage_results(source_results, target_results)

        self.assertFalse(comparison["valid"])
        self.assertIn(comparison["recommendation"], {"degraded", "unusable"})
        self.assertGreaterEqual(
            comparison["summary"]["degraded_scenarios"] + comparison["summary"]["unusable_scenarios"],
            1,
        )

    def test_reconstruct_script_dry_run_lists_full_pipeline(self) -> None:
        source = self._write_queryable_palace(name="source-palace")
        target = self.root / "target-palace"
        work_dir = self.root / "work-dir"

        result = self._run_reconstruct_script(
            "--source-palace",
            str(source),
            "--target-palace",
            str(target),
            "--work-dir",
            str(work_dir),
            "--source-python",
            str(REPO_ROOT / ".venv/bin/python"),
            "--target-python",
            str(REPO_ROOT / ".venv/bin/python"),
            "--with-usage",
            "--with-mcp-runtime",
            "--dry-run",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Step 1/10", result.stdout)
        self.assertIn("Step 10/10", result.stdout)
        self.assertIn("record-retrieval", result.stdout)
        self.assertIn("compare-usage", result.stdout)
        self.assertIn("validate-mcp-runtime", result.stdout)
        self.assertFalse(work_dir.exists())

    def test_reconstruct_script_runs_end_to_end(self) -> None:
        source = self._write_queryable_palace(name="source-palace")
        target = self.root / "target-palace"
        work_dir = self.root / "work-dir"

        result = self._run_reconstruct_script(
            "--source-palace",
            str(source),
            "--target-palace",
            str(target),
            "--work-dir",
            str(work_dir),
            "--source-python",
            str(REPO_ROOT / ".venv/bin/python"),
            "--target-python",
            str(REPO_ROOT / ".venv/bin/python"),
            "--with-usage",
            "--with-mcp-runtime",
        )

        combined_output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, msg=combined_output)
        self.assertTrue((target / TARGET_MANIFEST_FILENAME).exists())
        self.assertTrue((work_dir / "source-retrieval-results.json").exists())
        self.assertTrue((work_dir / "target-retrieval-results.json").exists())
        self.assertTrue((work_dir / "source-usage-results.json").exists())
        self.assertTrue((work_dir / "target-usage-results.json").exists())
        self.assertIn("Reconstruction validation passed", combined_output)
        self.assertIn("Retrieval validation passed", combined_output)
        self.assertIn("Usage comparison passed", combined_output)
        self.assertIn("MCP runtime validation passed", combined_output)

    def test_reconstruct_script_stops_on_export_failure(self) -> None:
        source = self._write_source_palace(
            [
                {
                    "row_id": 1,
                    "id": "drawer_a",
                    "document": "alpha text",
                    "metadata": {"wing": "proj", "room": "docs"},
                },
                {
                    "row_id": 2,
                    "id": "drawer_a",
                    "document": "beta text",
                    "metadata": {"wing": "proj", "room": "code"},
                },
            ]
        )
        target = self.root / "target-palace"
        work_dir = self.root / "work-dir"

        result = self._run_reconstruct_script(
            "--source-palace",
            str(source),
            "--target-palace",
            str(target),
            "--work-dir",
            str(work_dir),
            "--source-python",
            str(REPO_ROOT / ".venv/bin/python"),
            "--target-python",
            str(REPO_ROOT / ".venv/bin/python"),
        )

        combined_output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate source ids", combined_output)
        self.assertFalse((target / TARGET_MANIFEST_FILENAME).exists())
        self.assertFalse((work_dir / "source-retrieval-results.json").exists())

    def test_export_cli_error_includes_category_and_action(self) -> None:
        source = self._write_source_palace(
            [
                {
                    "row_id": 1,
                    "id": "drawer_a",
                    "document": "alpha text",
                    "metadata": {"wing": "proj", "room": "docs"},
                },
                {
                    "row_id": 2,
                    "id": "drawer_a",
                    "document": "beta text",
                    "metadata": {"wing": "proj", "room": "code"},
                },
            ]
        )
        export_dir = self.root / "export"

        result = self._run_prototype_script("export", "--source-palace", str(source), "--output-dir", str(export_dir))

        stderr = result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Export failed: source palace failed integrity checks before bundle generation", stderr)
        self.assertIn("Category: data integrity", stderr)
        self.assertIn("duplicate source ids", stderr)
        self.assertIn("Suggested action:", stderr)
        self.assertIn(str(source / "chroma.sqlite3"), stderr)

    def test_validate_cli_writes_debug_artifact_and_groups_errors(self) -> None:
        source = self._write_source_palace()
        export_dir = self.root / "export"
        target = self.root / "target"

        export_drawers(source, export_dir)
        import_drawers(export_dir, target)

        collection = self._open_target_collection(target)
        collection.delete(ids=["drawer_a", "drawer_b"])
        collection.add(
            ids=["drawer_a"],
            documents=["alpha text changed"],
            metadatas=[{"wing": "proj", "chunk_index": 0}],
        )
        collection.upsert(
            ids=["drawer_extra"],
            documents=["unexpected text"],
            metadatas=[{"wing": "proj", "room": "misc", "chunk_index": 9}],
        )

        result = self._run_prototype_script("validate", "--export-dir", str(export_dir), "--target-palace", str(target))

        combined_output = result.stdout + result.stderr
        debug_path = export_dir / VALIDATION_DEBUG_FILENAME
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Validation failure summary:", combined_output)
        self.assertIn("Structural:", combined_output)
        self.assertIn("Data integrity:", combined_output)
        self.assertIn("missing drawers in target", combined_output)
        self.assertIn("metadata mismatches", combined_output)
        self.assertTrue(debug_path.exists())

    def test_import_cli_error_includes_target_location_and_action(self) -> None:
        source = self._write_source_palace()
        export_dir = self.root / "export"
        target = self.root / "target"

        export_drawers(source, export_dir)
        target.mkdir()
        (target / "existing.txt").write_text("occupied", encoding="utf-8")

        result = self._run_prototype_script("import", "--export-dir", str(export_dir), "--target-palace", str(target))

        stderr = result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Import failed: target directory is not empty", stderr)
        self.assertIn("Category: structural", stderr)
        self.assertIn("existing entries: existing.txt", stderr)
        self.assertIn("Suggested action:", stderr)

    def test_compare_retrieval_cli_writes_debug_artifact_and_groups_errors(self) -> None:
        source = self._write_queryable_palace(name="source-palace")
        export_dir = self.root / "export"
        target = self.root / "target"
        source_results = self.root / "source-retrieval.json"
        target_results = self.root / "target-retrieval.json"

        export_drawers(source, export_dir)
        import_drawers(export_dir, target)

        collection = self._open_target_collection(target)
        collection.delete(ids=["drawer_alpha", "drawer_beta", "drawer_gamma"])
        collection.add(
            ids=["drawer_delta", "drawer_epsilon", "drawer_zeta"],
            documents=[
                "delta unrelated content about another topic",
                "epsilon unrelated content about another topic",
                "zeta unrelated content about another topic",
            ],
            metadatas=[
                {"wing": "other", "room": "misc", "chunk_index": 10},
                {"wing": "other", "room": "misc", "chunk_index": 11},
                {"wing": "other", "room": "misc", "chunk_index": 12},
            ],
        )

        record_retrieval_results(source, export_dir / RETRIEVAL_QUERIES_FILENAME, source_results, label="source")
        record_retrieval_results(target, export_dir / RETRIEVAL_QUERIES_FILENAME, target_results, label="target")

        result = self._run_prototype_script(
            "compare-retrieval",
            "--source-results",
            str(source_results),
            "--target-results",
            str(target_results),
        )

        combined_output = result.stdout + result.stderr
        debug_path = self.root / RETRIEVAL_DEBUG_FILENAME
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Retrieval failure summary:", combined_output)
        self.assertIn("Retrieval mismatch:", combined_output)
        self.assertIn("anchor=", combined_output)
        self.assertIn("Suggested action:", combined_output)
        self.assertTrue(debug_path.exists())


if __name__ == "__main__":
    unittest.main()
