#!/usr/bin/env python3
"""Tests for scripts/runtime_compat.py."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

# Allow import from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from runtime_compat import (
    CompatDiagnostic,
    PalaceFormat,
    VersionLine,
    classify_chromadb_version,
    is_compatible,
    probe_palace_format,
)


# ---------------------------------------------------------------------------
# classify_chromadb_version
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "version, expected",
    [
        ("0.6", "0.6.x"),
        ("0.6.3", "0.6.x"),
        ("0.6.10", "0.6.x"),
        ("1.0.0", "1.x"),
        ("1.5.7", "1.x"),
        ("1.12.3", "1.x"),
        ("1.0.0-rc1", "1.x"),
        ("2.0.0", "unknown"),
        ("0.5.0", "unknown"),
        ("abc", "unknown"),
    ],
)
def test_classify_chromadb_version(version: str, expected: VersionLine) -> None:
    assert classify_chromadb_version(version) == expected


# ---------------------------------------------------------------------------
# is_compatible
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fmt, line, expected",
    [
        ("0.6.x", "0.6.x", True),
        ("0.6.x", "1.x", True),
        ("1.x", "1.x", True),
        ("1.x", "0.6.x", False),
    ],
)
def test_is_compatible_known(fmt: PalaceFormat, line: VersionLine, expected: bool) -> None:
    assert is_compatible(fmt, line) == expected


def test_is_compatible_unknown_combo() -> None:
    assert is_compatible("empty", "0.6.x") is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# probe_palace_format
# ---------------------------------------------------------------------------

def _make_palace(tmp_path: Path, config_json_str: str) -> Path:
    palace = tmp_path / "palace"
    palace.mkdir()
    db = palace / "chroma.sqlite3"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE collections (id TEXT, name TEXT, config_json_str TEXT)"
    )
    conn.execute(
        "INSERT INTO collections VALUES (?, ?, ?)",
        ("1", "mempalace_drawers", config_json_str),
    )
    conn.commit()
    conn.close()
    return palace


def test_probe_06x(tmp_path: Path) -> None:
    config = json.dumps({"_type": "CollectionConfigurationInternal", "hnsw_configuration": {}})
    palace = _make_palace(tmp_path, config)
    assert probe_palace_format(palace) == "0.6.x"


def test_probe_1x(tmp_path: Path) -> None:
    palace = _make_palace(tmp_path, "{}")
    assert probe_palace_format(palace) == "1.x"


def test_probe_empty_no_db(tmp_path: Path) -> None:
    palace = tmp_path / "palace"
    palace.mkdir()
    assert probe_palace_format(palace) == "empty"


def test_probe_empty_table(tmp_path: Path) -> None:
    palace = tmp_path / "palace"
    palace.mkdir()
    db = palace / "chroma.sqlite3"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE collections (id TEXT, name TEXT, config_json_str TEXT)"
    )
    conn.commit()
    conn.close()
    assert probe_palace_format(palace) == "empty"
