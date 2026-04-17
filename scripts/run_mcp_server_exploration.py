#!/usr/bin/env python3

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def main() -> int:
    # Exploration-only launcher: intentionally skips the stable branch's
    # ChromaDB line check so a separate test environment can probe raw
    # MemPalace MCP startup behavior.
    #
    # Still performs a palace/runtime compatibility check and warns loudly
    # if the combination is known-incompatible.  Does NOT block — the user
    # explicitly opted into exploration mode.
    palace_path = os.environ.get("MEMPALACE_PALACE_PATH") or os.environ.get(
        "MEMPAL_PALACE_PATH", "~/.mempalace/palace"
    )
    path = Path(palace_path).expanduser().resolve()

    try:
        from runtime_compat import diagnose

        diag = diagnose(path)
        if not diag.compatible:
            print(
                f"[WARN]  Exploration mode — palace/runtime mismatch detected:\n"
                f"        {diag.message}\n"
                f"        {diag.action}\n"
                f"        Proceeding anyway because this is exploration mode.",
                file=sys.stderr,
            )
        else:
            print(
                f"[INFO]  palace_format={diag.palace_format} "
                f"runtime={diag.runtime_version} ({diag.runtime_line})",
                file=sys.stderr,
            )
    except ImportError:
        pass  # runtime_compat not available — skip gracefully

    runpy.run_module("mempalace.mcp_server", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
