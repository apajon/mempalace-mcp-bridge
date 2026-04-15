#!/usr/bin/env python3

from __future__ import annotations

import runpy
import sys

from check_chromadb_version import get_unsupported_reason
from palace_safety_gate import evaluate_palace_safety
from pathlib import Path
from mempalace.config import MempalaceConfig


def main() -> int:
    reason = get_unsupported_reason()
    if reason is not None:
        print(f"[ERROR] {reason}", file=sys.stderr)
        return 1

    palace_path = Path(MempalaceConfig().palace_path)
    gate = evaluate_palace_safety(palace_path, "read")
    if not gate.allowed:
        print(f"[ERROR] {gate.message}", file=sys.stderr)
        return 1

    runpy.run_module("mempalace.mcp_server", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
