#!/usr/bin/env python3

from __future__ import annotations

import runpy


def main() -> int:
    # Exploration-only launcher: intentionally skips the stable branch's
    # ChromaDB line check so a separate test environment can probe raw
    # MemPalace MCP startup behavior.
    runpy.run_module("mempalace.mcp_server", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
