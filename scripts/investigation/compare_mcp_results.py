#!/usr/bin/env python3
"""Compare two MCP runtime test results.

Reads the JSON outputs from mcp_runtime_test.py and produces a
structured diff report.

Usage:
    python compare_mcp_results.py <native.json> <reconstructed.json>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _extract_text(response: dict) -> str:
    """Extract text content from an MCP tool response."""
    if not response or "result" not in response:
        return ""
    content = response["result"].get("content", [])
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item["text"])
    return "\n".join(parts)


def _normalize_for_comparison(text: str) -> str:
    """Remove UUIDs and timestamps that differ between palaces."""
    # Remove UUIDs
    text = re.sub(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", "<UUID>", text)
    # Remove timestamps
    text = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "<TIMESTAMP>", text)
    return text


def _extract_search_ids(text: str) -> list[str]:
    """Extract drawer IDs from search results in order."""
    return re.findall(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", text)


def _extract_tool_names(response: dict) -> list[str]:
    """Extract tool names from tools/list response."""
    if not response or "result" not in response:
        return []
    tools = response["result"].get("tools", [])
    return sorted(t["name"] for t in tools)


def compare(native_path: str, recon_path: str) -> dict:
    native = json.loads(Path(native_path).read_text())
    recon = json.loads(Path(recon_path).read_text())

    report = {
        "summary": {},
        "phases": {},
        "divergences": [],
        "verdict": "IDENTICAL",
    }

    # ── Meta ──
    report["native_palace"] = native["palace_path"]
    report["reconstructed_palace"] = recon["palace_path"]
    report["native_python"] = native["python"]
    report["reconstructed_python"] = recon["python"]
    report["native_total_ms"] = native["total_time_ms"]
    report["reconstructed_total_ms"] = recon["total_time_ms"]
    report["native_exit"] = native["exit_code"]
    report["reconstructed_exit"] = recon["exit_code"]

    # ── Phase-by-phase comparison ──
    all_phases = set(native["phases"].keys()) | set(recon["phases"].keys())

    for phase in sorted(all_phases):
        n_phase = native["phases"].get(phase, {})
        r_phase = recon["phases"].get(phase, {})
        comparison = {"phase": phase, "status": "IDENTICAL"}

        # Check if phase missing in one
        if phase not in native["phases"]:
            comparison["status"] = "MISSING_IN_NATIVE"
            report["divergences"].append(f"{phase}: missing in native run")
            report["phases"][phase] = comparison
            continue
        if phase not in recon["phases"]:
            comparison["status"] = "MISSING_IN_RECONSTRUCTED"
            report["divergences"].append(f"{phase}: missing in reconstructed run")
            report["phases"][phase] = comparison
            continue

        # Check for skipped
        if n_phase.get("skipped") or r_phase.get("skipped"):
            comparison["status"] = "SKIPPED"
            comparison["native_skipped"] = n_phase.get("skipped", False)
            comparison["recon_skipped"] = r_phase.get("skipped", False)
            report["phases"][phase] = comparison
            continue

        n_resp = n_phase.get("response", {})
        r_resp = r_phase.get("response", {})

        # Check for errors
        n_err = n_resp.get("error")
        r_err = r_resp.get("error")
        if n_err or r_err:
            if n_err and r_err:
                comparison["status"] = "BOTH_ERROR"
                comparison["native_error"] = n_err
                comparison["recon_error"] = r_err
            elif n_err:
                comparison["status"] = "NATIVE_ERROR_ONLY"
                comparison["native_error"] = n_err
                report["divergences"].append(f"{phase}: error in native only: {n_err}")
            else:
                comparison["status"] = "RECON_ERROR_ONLY"
                comparison["recon_error"] = r_err
                report["divergences"].append(f"{phase}: error in reconstructed only: {r_err}")
            report["phases"][phase] = comparison
            continue

        # Latency
        comparison["native_ms"] = n_phase.get("latency_ms")
        comparison["recon_ms"] = r_phase.get("latency_ms")

        # Special handling for tools/list
        if phase == "tools_list":
            n_tools = n_phase.get("tool_names", [])
            r_tools = r_phase.get("tool_names", [])
            comparison["native_tool_count"] = len(n_tools)
            comparison["recon_tool_count"] = len(r_tools)
            if n_tools == r_tools:
                comparison["status"] = "IDENTICAL"
            else:
                comparison["status"] = "DIFFERENT"
                comparison["missing_in_recon"] = sorted(set(n_tools) - set(r_tools))
                comparison["extra_in_recon"] = sorted(set(r_tools) - set(n_tools))
                report["divergences"].append(
                    f"{phase}: tool lists differ — missing: {comparison['missing_in_recon']}, "
                    f"extra: {comparison['extra_in_recon']}"
                )
            report["phases"][phase] = comparison
            continue

        # Special handling for initialize
        if phase == "initialize":
            n_ver = n_resp.get("result", {}).get("protocolVersion")
            r_ver = r_resp.get("result", {}).get("protocolVersion")
            n_name = n_resp.get("result", {}).get("serverInfo", {}).get("name")
            r_name = r_resp.get("result", {}).get("serverInfo", {}).get("name")
            comparison["native_protocol"] = n_ver
            comparison["recon_protocol"] = r_ver
            comparison["native_server"] = n_name
            comparison["recon_server"] = r_name
            if n_ver == r_ver and n_name == r_name:
                comparison["status"] = "IDENTICAL"
            else:
                comparison["status"] = "DIFFERENT"
                report["divergences"].append(f"{phase}: protocol/server info differs")
            report["phases"][phase] = comparison
            continue

        # General content comparison
        n_text = _extract_text(n_resp)
        r_text = _extract_text(r_resp)
        n_norm = _normalize_for_comparison(n_text)
        r_norm = _normalize_for_comparison(r_text)

        if n_norm == r_norm:
            comparison["status"] = "IDENTICAL"
        else:
            # Check if same structure different UUIDs only
            n_ids = _extract_search_ids(n_text)
            r_ids = _extract_search_ids(r_text)

            # For search results: check if same content returned (possibly different IDs)
            if phase.startswith("search_"):
                # Extract just the content lines (skip IDs)
                n_content_lines = [l for l in n_text.splitlines() if not re.match(r"^[a-f0-9]{8}-", l)]
                r_content_lines = [l for l in r_text.splitlines() if not re.match(r"^[a-f0-9]{8}-", l)]
                n_content_norm = _normalize_for_comparison("\n".join(n_content_lines))
                r_content_norm = _normalize_for_comparison("\n".join(r_content_lines))

                if n_content_norm == r_content_norm:
                    comparison["status"] = "IDENTICAL_CONTENT_DIFFERENT_IDS"
                else:
                    comparison["status"] = "DIFFERENT"
                    comparison["native_preview"] = n_text[:500]
                    comparison["recon_preview"] = r_text[:500]
                    report["divergences"].append(f"{phase}: content differs")
            else:
                comparison["status"] = "DIFFERENT"
                comparison["native_preview"] = n_text[:500]
                comparison["recon_preview"] = r_text[:500]
                report["divergences"].append(f"{phase}: content differs")

        report["phases"][phase] = comparison

    # ── Verdict ──
    statuses = [p["status"] for p in report["phases"].values()]
    if all(s in ("IDENTICAL", "IDENTICAL_CONTENT_DIFFERENT_IDS", "SKIPPED") for s in statuses):
        if any(s == "IDENTICAL_CONTENT_DIFFERENT_IDS" for s in statuses):
            report["verdict"] = "IDENTICAL (different UUIDs only)"
        else:
            report["verdict"] = "IDENTICAL"
    elif any(s == "DIFFERENT" for s in statuses):
        report["verdict"] = "DIFFERENT"
    else:
        report["verdict"] = "PARTIALLY_IDENTICAL"

    report["summary"] = {
        "total_phases": len(report["phases"]),
        "identical": sum(1 for s in statuses if s == "IDENTICAL"),
        "identical_content": sum(1 for s in statuses if s == "IDENTICAL_CONTENT_DIFFERENT_IDS"),
        "different": sum(1 for s in statuses if s == "DIFFERENT"),
        "skipped": sum(1 for s in statuses if s == "SKIPPED"),
        "errors": sum(1 for s in statuses if "ERROR" in s),
        "divergence_count": len(report["divergences"]),
    }

    return report


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <native.json> <reconstructed.json>", file=sys.stderr)
        return 1

    report = compare(sys.argv[1], sys.argv[2])

    # Print human-readable summary
    print("=" * 60)
    print("MCP RUNTIME COMPARISON REPORT")
    print("=" * 60)
    print(f"Verdict: {report['verdict']}")
    print(f"Divergences: {report['summary']['divergence_count']}")
    print()

    s = report["summary"]
    print(f"Phases: {s['total_phases']} total")
    print(f"  Identical:         {s['identical']}")
    print(f"  Identical content: {s['identical_content']}")
    print(f"  Different:         {s['different']}")
    print(f"  Skipped:           {s['skipped']}")
    print(f"  Errors:            {s['errors']}")
    print()

    print("Phase detail:")
    for name, p in sorted(report["phases"].items()):
        status = p["status"]
        n_ms = p.get("native_ms", "?")
        r_ms = p.get("recon_ms", "?")
        print(f"  {name:30s}  {status:40s}  native={n_ms}ms  recon={r_ms}ms")

    if report["divergences"]:
        print()
        print("Divergences:")
        for d in report["divergences"]:
            print(f"  - {d}")

    # Also write full report as JSON
    report_path = "/tmp/mcp-comparison-report.json"
    Path(report_path).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nFull report: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
