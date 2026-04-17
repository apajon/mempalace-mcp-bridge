#!/usr/bin/env python3
"""Detect and report palace/runtime compatibility.

Centralised guard: given a palace path and the current runtime's chromadb
version, determine whether the palace is loadable and return a structured
diagnostic.

This module is imported by launchers and validation scripts.  It does NOT
depend on mempalace itself — only on the standard library and SQLite
inspection of the palace directory.
"""

from __future__ import annotations

import importlib.metadata
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Version classification
# ---------------------------------------------------------------------------

_RE_06 = re.compile(r"^0\.6(?:\.\d+)?$")
_RE_1X = re.compile(r"^1(?:\.\d+){1,}([.-].+)?$")

VersionLine = Literal["0.6.x", "1.x", "unknown"]


def classify_chromadb_version(version: str) -> VersionLine:
    """Return the compatibility line for a chromadb version string."""
    if _RE_06.fullmatch(version):
        return "0.6.x"
    if _RE_1X.fullmatch(version):
        return "1.x"
    return "unknown"


def current_chromadb_version() -> str | None:
    """Return the installed chromadb version, or None if unavailable."""
    try:
        return importlib.metadata.version("chromadb")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Palace format probing (lightweight — no ChromaDB import)
# ---------------------------------------------------------------------------

PalaceFormat = Literal["0.6.x", "1.x", "empty", "unreadable"]


def probe_palace_format(palace_path: Path) -> PalaceFormat:
    """Inspect config_json_str to infer which chromadb line wrote the palace."""
    db = palace_path / "chroma.sqlite3"
    if not db.exists():
        return "empty"
    try:
        conn = sqlite3.connect(str(db))
        cur = conn.cursor()
        cur.execute("SELECT config_json_str FROM collections LIMIT 1")
        row = cur.fetchone()
        conn.close()
    except Exception:
        return "unreadable"

    if row is None:
        return "empty"

    config_str = row[0] or "{}"
    try:
        config = json.loads(config_str)
    except json.JSONDecodeError:
        return "unreadable"

    if config.get("_type") == "CollectionConfigurationInternal":
        return "0.6.x"
    # 1.x stores '{}' — empty dict without _type
    if isinstance(config, dict) and "_type" not in config:
        return "1.x"
    return "unreadable"


# ---------------------------------------------------------------------------
# Compatibility matrix
# ---------------------------------------------------------------------------

# Can this runtime load a palace in this format?
#   (palace_format, runtime_line) -> loadable?
_COMPAT: dict[tuple[PalaceFormat, VersionLine], bool] = {
    ("0.6.x", "0.6.x"): True,
    ("0.6.x", "1.x"): True,   # forward-compatible
    ("1.x", "1.x"): True,
    ("1.x", "0.6.x"): False,  # the _type KeyError trap
}


def is_compatible(palace_format: PalaceFormat, runtime_line: VersionLine) -> bool | None:
    """Return True/False if the combination is known, None if unknown."""
    return _COMPAT.get((palace_format, runtime_line))


# ---------------------------------------------------------------------------
# Diagnostic result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompatDiagnostic:
    compatible: bool
    palace_format: PalaceFormat
    runtime_version: str
    runtime_line: VersionLine
    message: str
    action: str  # empty if compatible


def diagnose(palace_path: Path) -> CompatDiagnostic:
    """Full diagnostic: probe palace, check runtime, return verdict."""
    version = current_chromadb_version()
    if version is None:
        return CompatDiagnostic(
            compatible=False,
            palace_format="unreadable",
            runtime_version="(not installed)",
            runtime_line="unknown",
            message="chromadb is not installed in the current environment.",
            action="Run: bash setup.sh",
        )

    runtime_line = classify_chromadb_version(version)
    palace_format = probe_palace_format(palace_path)

    if palace_format in ("empty", "unreadable"):
        return CompatDiagnostic(
            compatible=True,  # nothing to conflict with
            palace_format=palace_format,
            runtime_version=version,
            runtime_line=runtime_line,
            message=f"Palace at {palace_path} is {palace_format}; no compatibility conflict.",
            action="",
        )

    compat = is_compatible(palace_format, runtime_line)
    if compat is True:
        return CompatDiagnostic(
            compatible=True,
            palace_format=palace_format,
            runtime_version=version,
            runtime_line=runtime_line,
            message=(
                f"Palace format {palace_format} is compatible with "
                f"chromadb {version} ({runtime_line})."
            ),
            action="",
        )

    if compat is False:
        if palace_format == "1.x" and runtime_line == "0.6.x":
            return CompatDiagnostic(
                compatible=False,
                palace_format=palace_format,
                runtime_version=version,
                runtime_line=runtime_line,
                message=(
                    f"Palace at {palace_path} was created with chromadb 1.x "
                    f"(config_json_str lacks '_type'), but this runtime uses "
                    f"chromadb {version} (0.6.x line). "
                    f"ChromaDB 0.6.x cannot load 1.x-format palaces — "
                    f"it will fail with KeyError: '_type' in "
                    f"ConfigurationInternal.from_json()."
                ),
                action=(
                    "Use a chromadb 1.x environment to load this palace, "
                    "or reconstruct it for 0.6.x. "
                    "See: docs/troubleshooting.md#chromadb-version-incompatibility"
                ),
            )
        return CompatDiagnostic(
            compatible=False,
            palace_format=palace_format,
            runtime_version=version,
            runtime_line=runtime_line,
            message=(
                f"Palace format {palace_format} is incompatible with "
                f"chromadb {version} ({runtime_line})."
            ),
            action="Check runtime environment matches the palace format.",
        )

    # Unknown combination
    return CompatDiagnostic(
        compatible=True,  # don't block, but warn
        palace_format=palace_format,
        runtime_version=version,
        runtime_line=runtime_line,
        message=(
            f"Could not confirm compatibility between palace format "
            f"{palace_format} and chromadb {version} ({runtime_line}). "
            f"Proceeding, but failures may occur."
        ),
        action="",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <palace_path>", file=sys.stderr)
        return 1

    path = Path(sys.argv[1]).expanduser().resolve()
    diag = diagnose(path)

    status = "[OK]   " if diag.compatible else "[ERROR]"
    print(f"{status} {diag.message}")
    if diag.action:
        print(f"       {diag.action}")
    print(f"       palace_format={diag.palace_format} runtime={diag.runtime_version} ({diag.runtime_line})")

    return 0 if diag.compatible else 1


if __name__ == "__main__":
    raise SystemExit(main())
