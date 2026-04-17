#!/usr/bin/env python3
"""Robustness test harness for the reconstruction pipeline.

Runs each adversarial palace through the export → import → validate cycle
and classifies outcomes into:
  - full_success:    export + import + validation all pass
  - degraded:        export succeeds with warnings, import OK, some validation quirks
  - partial_failure: export fails gracefully with clear error
  - hard_failure:    unhandled exception or silent corruption

Writes a structured JSON report and a markdown matrix.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
INVESTIGATION_DIR = Path(__file__).resolve().parent
for _p in (str(SCRIPTS_DIR), str(INVESTIGATION_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from adversarial_palaces import ALL_GENERATORS
from palace_reconstruction_prototype import (
    ReconstructionCliError,
    export_drawers,
    extract_drawers_from_sqlite,
    import_drawers,
    summarize_drawers,
    validate_reconstruction,
)

OUTCOME_FULL_SUCCESS = "full_success"
OUTCOME_DEGRADED = "degraded"
OUTCOME_PARTIAL_FAILURE = "partial_failure"
OUTCOME_HARD_FAILURE = "hard_failure"


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_case(case_info: dict[str, Any], work_root: Path) -> dict[str, Any]:
    """Run full export→import→validate for one adversarial palace."""
    palace_path = Path(case_info["palace"])
    case_name = case_info["case"]
    export_dir = work_root / case_name / "export"
    target_dir = work_root / case_name / "target"

    result: dict[str, Any] = {
        "case": case_name,
        "defect": case_info.get("defect"),
        "source_drawer_count": case_info.get("drawer_count", 0),
        "stages": {},
        "outcome": None,
        "outcome_reason": None,
        "root_cause_class": None,
        "error_message": None,
        "traceback": None,
    }

    # --- Stage 1: extract_drawers_from_sqlite ---
    try:
        db_path = palace_path / "chroma.sqlite3"
        if not db_path.exists():
            result["stages"]["extract"] = {"status": "skipped", "reason": "no chroma.sqlite3"}
            result["outcome"] = OUTCOME_PARTIAL_FAILURE
            result["outcome_reason"] = "missing sqlite file"
            result["root_cause_class"] = "expected_limitation"
            result["error_message"] = "Source palace has no chroma.sqlite3"
            return result

        drawers = extract_drawers_from_sqlite(db_path)
        result["stages"]["extract"] = {
            "status": "ok",
            "drawer_count": len(drawers),
            "sample_ids": [d["id"] for d in drawers[:5]],
        }
    except ReconstructionCliError as exc:
        result["stages"]["extract"] = {"status": "error", "error": str(exc)}
        result["outcome"] = OUTCOME_PARTIAL_FAILURE
        result["outcome_reason"] = f"extract rejected: {exc.summary}"
        result["root_cause_class"] = _classify_cli_error(exc)
        result["error_message"] = str(exc)
        return result
    except Exception as exc:
        result["stages"]["extract"] = {"status": "error", "error": str(exc)}
        result["outcome"] = OUTCOME_HARD_FAILURE
        result["outcome_reason"] = f"extract crashed: {exc}"
        result["root_cause_class"] = _classify_extract_error(exc)
        result["error_message"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result

    # --- Stage 2: export_drawers ---
    try:
        export_manifest = export_drawers(palace_path, export_dir)
        result["stages"]["export"] = {
            "status": "ok",
            "drawer_count": export_manifest.get("summary", {}).get("drawer_count", 0),
            "warnings": export_manifest.get("warnings", []),
        }
    except ReconstructionCliError as exc:
        result["stages"]["export"] = {
            "status": "rejected",
            "stage": exc.stage,
            "category": exc.category,
            "summary": exc.summary,
            "details": exc.details,
        }
        result["outcome"] = OUTCOME_PARTIAL_FAILURE
        result["outcome_reason"] = f"export rejected: {exc.summary}"
        result["root_cause_class"] = _classify_cli_error(exc)
        result["error_message"] = str(exc)
        return result
    except Exception as exc:
        result["stages"]["export"] = {"status": "crash", "error": str(exc)}
        result["outcome"] = OUTCOME_HARD_FAILURE
        result["outcome_reason"] = f"export crashed: {exc}"
        result["root_cause_class"] = "fixable_bug"
        result["error_message"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result

    # --- Stage 3: import_drawers ---
    try:
        import_manifest = import_drawers(export_dir, target_dir)
        imported_count = import_manifest.get("target", {}).get("imported_drawer_count", 0)
        result["stages"]["import"] = {
            "status": "ok",
            "imported_drawer_count": imported_count,
        }
    except ReconstructionCliError as exc:
        result["stages"]["import"] = {
            "status": "rejected",
            "stage": exc.stage,
            "category": exc.category,
            "summary": exc.summary,
            "details": exc.details,
        }
        result["outcome"] = OUTCOME_PARTIAL_FAILURE
        result["outcome_reason"] = f"import rejected: {exc.summary}"
        result["root_cause_class"] = _classify_cli_error(exc)
        result["error_message"] = str(exc)
        return result
    except Exception as exc:
        result["stages"]["import"] = {"status": "crash", "error": str(exc)}
        result["outcome"] = OUTCOME_HARD_FAILURE
        result["outcome_reason"] = f"import crashed: {exc}"
        result["root_cause_class"] = "fixable_bug"
        result["error_message"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result

    # --- Stage 4: validate_reconstruction ---
    try:
        validation = validate_reconstruction(export_dir, target_dir)
        val_summary = validation.get("summary", {})
        errors = val_summary.get("error_groups", [])
        warnings_list = val_summary.get("warnings", [])

        result["stages"]["validate"] = {
            "status": "ok" if not errors else "errors",
            "drawer_match": val_summary.get("drawer_match"),
            "document_match_ratio": val_summary.get("document_match_ratio"),
            "metadata_match_ratio": val_summary.get("metadata_match_ratio"),
            "error_count": len(errors),
            "warning_count": len(warnings_list) if isinstance(warnings_list, list) else 0,
        }

        if not errors:
            if result["stages"]["export"].get("warnings"):
                result["outcome"] = OUTCOME_DEGRADED
                result["outcome_reason"] = "export succeeded with warnings, validation passed"
            else:
                result["outcome"] = OUTCOME_FULL_SUCCESS
                result["outcome_reason"] = "all stages passed cleanly"
        else:
            result["outcome"] = OUTCOME_DEGRADED
            result["outcome_reason"] = f"validation found {len(errors)} error group(s)"

    except ReconstructionCliError as exc:
        result["stages"]["validate"] = {
            "status": "rejected",
            "stage": exc.stage,
            "category": exc.category,
            "summary": exc.summary,
        }
        result["outcome"] = OUTCOME_PARTIAL_FAILURE
        result["outcome_reason"] = f"validation rejected: {exc.summary}"
        result["root_cause_class"] = _classify_cli_error(exc)
        result["error_message"] = str(exc)
        return result
    except Exception as exc:
        result["stages"]["validate"] = {"status": "crash", "error": str(exc)}
        result["outcome"] = OUTCOME_HARD_FAILURE
        result["outcome_reason"] = f"validation crashed: {exc}"
        result["root_cause_class"] = "fixable_bug"
        result["error_message"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result

    # --- Stage 5: integrity cross-check (silent corruption detection) ---
    try:
        source_drawers = drawers
        import chromadb

        client = chromadb.PersistentClient(path=str(target_dir))
        collection = client.get_collection("mempalace_drawers")
        target_all = collection.get(include=["documents", "metadatas"])
        target_ids = set(target_all["ids"])
        source_ids = {d["id"] for d in source_drawers}

        missing_in_target = source_ids - target_ids
        extra_in_target = target_ids - source_ids

        # Check document content preservation
        target_docs = dict(zip(target_all["ids"], target_all["documents"]))
        content_mismatches = []
        for d in source_drawers:
            if d["id"] in target_docs and d["document"] != target_docs[d["id"]]:
                content_mismatches.append(d["id"])

        result["stages"]["integrity_crosscheck"] = {
            "status": "ok" if not (missing_in_target or extra_in_target or content_mismatches) else "mismatch",
            "source_id_count": len(source_ids),
            "target_id_count": len(target_ids),
            "missing_in_target": sorted(missing_in_target),
            "extra_in_target": sorted(extra_in_target),
            "content_mismatches": sorted(content_mismatches),
        }

        if content_mismatches:
            result["outcome"] = OUTCOME_HARD_FAILURE
            result["outcome_reason"] = f"SILENT CORRUPTION: {len(content_mismatches)} document(s) changed content"
            result["root_cause_class"] = "fixable_bug"

    except Exception as exc:
        result["stages"]["integrity_crosscheck"] = {"status": "error", "error": str(exc)}

    return result


def _classify_extract_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "no such table" in msg or "not a database" in msg:
        return "expected_limitation"
    return "fixable_bug"


def _classify_cli_error(exc: ReconstructionCliError) -> str:
    cat = exc.category.lower()
    if cat == "structural":
        return "expected_limitation"
    if cat == "data integrity":
        return "expected_limitation"
    return "upstream_constraint"


def run_all_cases(output_dir: Path | None = None) -> dict[str, Any]:
    """Generate all adversarial palaces, run them, collect results."""
    work_root = Path(tempfile.mkdtemp(prefix="robustness_"))
    palace_root = work_root / "palaces"
    pipeline_root = work_root / "pipeline"
    palace_root.mkdir()
    pipeline_root.mkdir()

    print(f"Work directory: {work_root}")
    print(f"Generating {len(ALL_GENERATORS)} adversarial palaces...")

    cases: list[dict[str, Any]] = []
    for gen_fn in ALL_GENERATORS:
        info = gen_fn(palace_root)
        cases.append(info)
        print(f"  [{info['case']}] drawers={info['drawer_count']}")

    print(f"\nRunning {len(cases)} cases through export→import→validate...\n")

    results: list[dict[str, Any]] = []
    counts = {OUTCOME_FULL_SUCCESS: 0, OUTCOME_DEGRADED: 0, OUTCOME_PARTIAL_FAILURE: 0, OUTCOME_HARD_FAILURE: 0}

    for case_info in cases:
        case_name = case_info["case"]
        print(f"  [{case_name}] ", end="", flush=True)
        try:
            result = _run_case(case_info, pipeline_root)
        except Exception as exc:
            result = {
                "case": case_name,
                "defect": case_info.get("defect"),
                "outcome": OUTCOME_HARD_FAILURE,
                "outcome_reason": f"harness-level crash: {exc}",
                "root_cause_class": "fixable_bug",
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
                "stages": {},
            }
        outcome = result["outcome"] or OUTCOME_HARD_FAILURE
        counts[outcome] = counts.get(outcome, 0) + 1
        status_icon = {"full_success": "✓", "degraded": "~", "partial_failure": "✗", "hard_failure": "!!"}
        print(f"{status_icon.get(outcome, '?')} {outcome}: {result.get('outcome_reason', '')}")
        results.append(result)

    report = {
        "created_at": _iso_now(),
        "work_directory": str(work_root),
        "case_count": len(results),
        "outcome_counts": counts,
        "results": results,
    }

    # Write JSON report
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "robustness_test_results.json"
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
            f.write("\n")
        print(f"\nJSON report: {json_path}")

    # Summary
    print(f"\n{'='*60}")
    print(f"ROBUSTNESS TEST SUMMARY")
    print(f"{'='*60}")
    print(f"  Total cases:      {len(results)}")
    print(f"  Full success:     {counts[OUTCOME_FULL_SUCCESS]}")
    print(f"  Degraded:         {counts[OUTCOME_DEGRADED]}")
    print(f"  Partial failure:  {counts[OUTCOME_PARTIAL_FAILURE]}")
    print(f"  Hard failure:     {counts[OUTCOME_HARD_FAILURE]}")

    silent_corruptions = [r for r in results if "SILENT CORRUPTION" in (r.get("outcome_reason") or "")]
    if silent_corruptions:
        print(f"\n  ⚠ SILENT CORRUPTIONS DETECTED: {len(silent_corruptions)}")
        for r in silent_corruptions:
            print(f"    - {r['case']}: {r['outcome_reason']}")
    else:
        print(f"\n  No silent corruption detected.")

    # Cleanup temp palaces (keep pipeline artifacts for inspection)
    shutil.rmtree(palace_root, ignore_errors=True)

    return report


def generate_markdown_matrix(report: dict[str, Any]) -> str:
    """Generate a markdown robustness matrix from the JSON report."""
    lines = [
        "# Migration Robustness Matrix",
        "",
        f"Generated: {report['created_at']}",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total cases | {report['case_count']} |",
        f"| Full success | {report['outcome_counts'].get('full_success', 0)} |",
        f"| Degraded | {report['outcome_counts'].get('degraded', 0)} |",
        f"| Partial failure | {report['outcome_counts'].get('partial_failure', 0)} |",
        f"| Hard failure | {report['outcome_counts'].get('hard_failure', 0)} |",
        "",
        "## Outcome Legend",
        "",
        "| Outcome | Meaning |",
        "|---------|---------|",
        "| `full_success` | Export + import + validation all pass cleanly |",
        "| `degraded` | Pipeline completes but with warnings or validation quirks |",
        "| `partial_failure` | Pipeline rejects input with clear, diagnosable error |",
        "| `hard_failure` | Unhandled exception or silent data corruption |",
        "",
        "## Root Cause Classes",
        "",
        "| Class | Meaning |",
        "|-------|---------|",
        "| `expected_limitation` | Pipeline correctly rejects unsupported input |",
        "| `fixable_bug` | Pipeline should handle this better |",
        "| `upstream_constraint` | ChromaDB or mempalace limitation beyond our control |",
        "",
        "## Detailed Results",
        "",
        "| Case | Defect | Drawers | Outcome | Stage Failed | Root Cause | Detail |",
        "|------|--------|---------|---------|-------------|------------|--------|",
    ]

    for r in report["results"]:
        case = r["case"]
        defect = r.get("defect") or "none (control)"
        drawers = r.get("source_drawer_count", "?")
        outcome = r.get("outcome", "?")
        root_cause = r.get("root_cause_class") or "—"

        # Find the stage that failed
        failed_stage = "—"
        stages = r.get("stages", {})
        for stage_name in ("extract", "export", "import", "validate", "integrity_crosscheck"):
            stage_data = stages.get(stage_name, {})
            if stage_data.get("status") in ("error", "rejected", "crash", "mismatch"):
                failed_stage = stage_name
                break

        detail = (r.get("outcome_reason") or "").replace("|", "\\|")
        if len(detail) > 80:
            detail = detail[:77] + "..."

        outcome_icon = {
            "full_success": "✅",
            "degraded": "⚠️",
            "partial_failure": "🚫",
            "hard_failure": "💥",
        }.get(outcome, "❓")

        lines.append(
            f"| `{case}` | {defect} | {drawers} | {outcome_icon} `{outcome}` | {failed_stage} | `{root_cause}` | {detail} |"
        )

    # --- Robustness boundaries ---
    lines.extend(
        [
            "",
            "## Robustness Boundaries",
            "",
            "### Guaranteed to work",
            "",
        ]
    )

    guaranteed = [r for r in report["results"] if r.get("outcome") == "full_success"]
    if guaranteed:
        for r in guaranteed:
            lines.append(f"- **{r['case']}**: {r.get('defect') or 'clean data'}")
    else:
        lines.append("- _(none)_")

    lines.extend(
        [
            "",
            "### Best-effort (degraded but usable)",
            "",
        ]
    )
    degraded = [r for r in report["results"] if r.get("outcome") == "degraded"]
    if degraded:
        for r in degraded:
            lines.append(f"- **{r['case']}**: {r.get('outcome_reason', '')}")
    else:
        lines.append("- _(none)_")

    lines.extend(
        [
            "",
            "### Correctly rejected (partial failure)",
            "",
        ]
    )
    partial = [r for r in report["results"] if r.get("outcome") == "partial_failure"]
    if partial:
        for r in partial:
            lines.append(f"- **{r['case']}**: {r.get('outcome_reason', '')}")
    else:
        lines.append("- _(none)_")

    lines.extend(
        [
            "",
            "### Bugs / Silent corruption (hard failure)",
            "",
        ]
    )
    hard = [r for r in report["results"] if r.get("outcome") == "hard_failure"]
    if hard:
        for r in hard:
            lines.append(f"- **{r['case']}**: {r.get('outcome_reason', '')}")
    else:
        lines.append("- _(none — no silent corruption detected)_")

    # --- Recommendations ---
    lines.extend(
        [
            "",
            "## Recommendations",
            "",
        ]
    )

    bugs = [r for r in report["results"] if r.get("root_cause_class") == "fixable_bug"]
    if bugs:
        lines.append("### Fixable bugs")
        lines.append("")
        for r in bugs:
            lines.append(f"1. **{r['case']}**: {r.get('outcome_reason', '')}")
        lines.append("")

    expected = [r for r in report["results"] if r.get("root_cause_class") == "expected_limitation"]
    if expected:
        lines.append("### Expected limitations (document as unsupported)")
        lines.append("")
        for r in expected:
            lines.append(f"- `{r['case']}`: {r.get('error_message', r.get('outcome_reason', ''))}")
        lines.append("")

    upstream = [r for r in report["results"] if r.get("root_cause_class") == "upstream_constraint"]
    if upstream:
        lines.append("### Upstream constraints")
        lines.append("")
        for r in upstream:
            lines.append(f"- `{r['case']}`: {r.get('outcome_reason', '')}")
        lines.append("")

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("investigation")
    report = run_all_cases(output_dir=output_dir)
    md = generate_markdown_matrix(report)
    md_path = output_dir / "migration_robustness_matrix.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"Markdown matrix: {md_path}")
