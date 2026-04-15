#!/usr/bin/env python3

from __future__ import annotations

import importlib.metadata
import re
import sys


SUPPORTED_LINE = "0.6.x"


def get_unsupported_reason() -> str | None:
    try:
        version = importlib.metadata.version("chromadb")
    except importlib.metadata.PackageNotFoundError:
        return "chromadb is not installed in .venv. Run: bash setup.sh"
    except Exception as exc:
        return f"could not read chromadb version ({exc}). Run: bash setup.sh"

    if re.fullmatch(r"0\.6(?:\.\d+)?", version):
        return None

    return (
        f"unsupported chromadb {version}. This stable branch supports {SUPPORTED_LINE} only. "
        "Run: bash update.sh"
    )


def main() -> int:
    reason = get_unsupported_reason()
    if reason is None:
        version = importlib.metadata.version("chromadb")
        print(f"[OK]    chromadb {version} is on the supported {SUPPORTED_LINE} line")
        return 0

    print(f"[ERROR] {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
