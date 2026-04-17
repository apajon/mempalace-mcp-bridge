#!/usr/bin/env python3
"""MCP runtime test harness.

Starts a real MemPalace MCP server as a subprocess, sends JSON-RPC
requests over stdio, records all responses.  Designed to be run twice
— once per palace — and outputs a structured JSON log for comparison.

Usage:
    <python> mcp_runtime_test.py <palace_path> <output_json>

Environment:
    PYTHONPATH must include the scripts/ directory so that the MCP
    launcher can import its sibling modules.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────

def _send(proc: subprocess.Popen, request: dict) -> dict | None:
    """Send a JSON-RPC request and read the response line."""
    line = json.dumps(request) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()

    # Notifications have no response
    if "id" not in request:
        time.sleep(0.1)
        return None

    # Read response with timeout
    response_line = proc.stdout.readline()
    if not response_line:
        raise RuntimeError("Server closed stdout unexpectedly")
    return json.loads(response_line.strip())


def _tool_call(proc: subprocess.Popen, req_id: int, name: str, args: dict | None = None) -> dict:
    """Send a tools/call request."""
    return _send(proc, {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": args or {}},
    })


# ── test sequences ──────────────────────────────────────────────────

def run_test_sequence(proc: subprocess.Popen) -> dict:
    """Execute the full test sequence and return structured results."""
    results = {}
    req_id = 1

    # ── Phase 1: Initialize ──────────────────────────────────────────
    t0 = time.monotonic()
    resp = _send(proc, {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    })
    t1 = time.monotonic()
    results["initialize"] = {
        "response": resp,
        "latency_ms": round((t1 - t0) * 1000, 1),
    }
    req_id += 1

    # Send initialized notification (no response expected)
    _send(proc, {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    })

    # ── Phase 2: List tools ──────────────────────────────────────────
    t0 = time.monotonic()
    resp = _send(proc, {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/list",
    })
    t1 = time.monotonic()
    tool_names = []
    if resp and "result" in resp:
        tool_names = [t["name"] for t in resp["result"].get("tools", [])]
    results["tools_list"] = {
        "response": resp,
        "tool_names": sorted(tool_names),
        "tool_count": len(tool_names),
        "latency_ms": round((t1 - t0) * 1000, 1),
    }
    req_id += 1

    # ── Phase 3: mempalace_status ────────────────────────────────────
    t0 = time.monotonic()
    resp = _tool_call(proc, req_id, "mempalace_status")
    t1 = time.monotonic()
    results["status"] = {
        "response": resp,
        "latency_ms": round((t1 - t0) * 1000, 1),
    }
    req_id += 1

    # ── Phase 4: mempalace_list_wings ────────────────────────────────
    t0 = time.monotonic()
    resp = _tool_call(proc, req_id, "mempalace_list_wings")
    t1 = time.monotonic()
    results["list_wings"] = {
        "response": resp,
        "latency_ms": round((t1 - t0) * 1000, 1),
    }
    req_id += 1

    # ── Phase 5: mempalace_list_rooms (for first wing) ───────────────
    t0 = time.monotonic()
    resp = _tool_call(proc, req_id, "mempalace_list_rooms", {"wing": "project_alpha"})
    t1 = time.monotonic()
    results["list_rooms"] = {
        "response": resp,
        "latency_ms": round((t1 - t0) * 1000, 1),
    }
    req_id += 1

    # ── Phase 6: mempalace_get_taxonomy ──────────────────────────────
    t0 = time.monotonic()
    resp = _tool_call(proc, req_id, "mempalace_get_taxonomy")
    t1 = time.monotonic()
    results["taxonomy"] = {
        "response": resp,
        "latency_ms": round((t1 - t0) * 1000, 1),
    }
    req_id += 1

    # ── Phase 7: mempalace_list_drawers ──────────────────────────────
    t0 = time.monotonic()
    resp = _tool_call(proc, req_id, "mempalace_list_drawers", {"limit": 5})
    t1 = time.monotonic()
    results["list_drawers"] = {
        "response": resp,
        "latency_ms": round((t1 - t0) * 1000, 1),
    }
    req_id += 1

    # ── Phase 8-10: Semantic searches (3 diverse queries) ────────────
    queries = [
        {"query": "database connection pooling", "limit": 5},
        {"query": "ROS 2 navigation behavior tree", "limit": 5},
        {"query": "Docker multi-stage build", "limit": 5},
    ]
    for i, q in enumerate(queries):
        t0 = time.monotonic()
        resp = _tool_call(proc, req_id, "mempalace_search", q)
        t1 = time.monotonic()
        results[f"search_{i+1}"] = {
            "query": q["query"],
            "response": resp,
            "latency_ms": round((t1 - t0) * 1000, 1),
        }
        req_id += 1

    # ── Phase 11: mempalace_search with wing filter ──────────────────
    t0 = time.monotonic()
    resp = _tool_call(proc, req_id, "mempalace_search", {
        "query": "architecture decision",
        "wing": "project_alpha",
        "limit": 3,
    })
    t1 = time.monotonic()
    results["search_filtered"] = {
        "query": "architecture decision (wing=project_alpha)",
        "response": resp,
        "latency_ms": round((t1 - t0) * 1000, 1),
    }
    req_id += 1

    # ── Phase 12: mempalace_check_duplicate ───────────────────────────
    t0 = time.monotonic()
    resp = _tool_call(proc, req_id, "mempalace_check_duplicate", {
        "content": "The project uses microservices with gRPC for inter-service communication",
    })
    t1 = time.monotonic()
    results["check_duplicate"] = {
        "response": resp,
        "latency_ms": round((t1 - t0) * 1000, 1),
    }
    req_id += 1

    # ── Phase 13: mempalace_get_drawer (first drawer from list) ──────
    # Extract a drawer ID from the list_drawers result
    drawer_id = None
    try:
        list_resp = results["list_drawers"]["response"]
        content_text = ""
        if "result" in list_resp:
            for item in list_resp["result"].get("content", []):
                if item.get("type") == "text":
                    content_text = item["text"]
                    break
        # Try to extract a drawer_id from the JSON text
        import re
        id_match = re.search(r'"drawer_id":\s*"([^"]+)"', content_text)
        if id_match:
            drawer_id = id_match.group(1)
    except Exception:
        pass

    if drawer_id:
        t0 = time.monotonic()
        resp = _tool_call(proc, req_id, "mempalace_get_drawer", {"drawer_id": drawer_id})
        t1 = time.monotonic()
        results["get_drawer"] = {
            "drawer_id": drawer_id,
            "response": resp,
            "latency_ms": round((t1 - t0) * 1000, 1),
        }
        req_id += 1
    else:
        results["get_drawer"] = {"skipped": True, "reason": "Could not extract drawer_id"}

    # ── Phase 14: mempalace_graph_stats ───────────────────────────────
    t0 = time.monotonic()
    resp = _tool_call(proc, req_id, "mempalace_graph_stats")
    t1 = time.monotonic()
    results["graph_stats"] = {
        "response": resp,
        "latency_ms": round((t1 - t0) * 1000, 1),
    }
    req_id += 1

    # ── Phase 15: mempalace_kg_stats ─────────────────────────────────
    t0 = time.monotonic()
    resp = _tool_call(proc, req_id, "mempalace_kg_stats")
    t1 = time.monotonic()
    results["kg_stats"] = {
        "response": resp,
        "latency_ms": round((t1 - t0) * 1000, 1),
    }
    req_id += 1

    return results


# ── main ─────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <palace_path> <output_json>", file=sys.stderr)
        return 1

    palace_path = Path(sys.argv[1]).resolve()
    output_path = Path(sys.argv[2])

    if not palace_path.exists():
        print(f"[ERROR] Palace not found: {palace_path}", file=sys.stderr)
        return 1

    python = sys.executable
    scripts_dir = Path(__file__).resolve().parent.parent  # scripts/
    server_script = scripts_dir / "run_mcp_server_exploration.py"

    env = os.environ.copy()
    env["MEMPALACE_PALACE_PATH"] = str(palace_path)
    env["PYTHONPATH"] = str(scripts_dir) + os.pathsep + env.get("PYTHONPATH", "")

    print(f"[INFO] Palace: {palace_path}", file=sys.stderr)
    print(f"[INFO] Python: {python}", file=sys.stderr)
    print(f"[INFO] Server: {server_script}", file=sys.stderr)

    # Start MCP server
    proc = subprocess.Popen(
        [python, str(server_script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1,
    )

    try:
        t_start = time.monotonic()
        results = run_test_sequence(proc)
        t_total = time.monotonic() - t_start

        # Collect stderr
        proc.stdin.close()
        stderr_output = proc.stderr.read()
        proc.wait(timeout=5)

        report = {
            "palace_path": str(palace_path),
            "python": python,
            "total_time_ms": round(t_total * 1000, 1),
            "exit_code": proc.returncode,
            "stderr": stderr_output,
            "phases": results,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"[OK] Results written to {output_path}", file=sys.stderr)
        return 0

    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        # Try to get stderr for diagnostics
        try:
            proc.kill()
            stderr_output = proc.stderr.read()
            print(f"[STDERR] {stderr_output}", file=sys.stderr)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
