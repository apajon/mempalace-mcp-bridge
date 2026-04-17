#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


MANIFEST_FILENAME = "mempalace-bridge-manifest.json"
CHROMA_SQLITE_FILENAME = "chroma.sqlite3"

CLASS_CHROMA_0_6 = "chroma_0_6"
CLASS_CHROMA_1_X = "chroma_1_x"
CLASS_UNKNOWN = "unknown"

_CHROMA_0_6_VERSION_RE = re.compile(r"^0\.6(?:\.\d+)?$")
_CHROMA_1_X_VERSION_RE = re.compile(r"^1(?:\.\d+){1,}([.-].+)?$")


@dataclass(frozen=True)
class DetectionEvidence:
    source: str
    detail: str


@dataclass(frozen=True)
class DetectionResult:
    palace_path: str
    classification: str
    confidence: str
    evidence: list[DetectionEvidence]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "palace_path": self.palace_path,
            "classification": self.classification,
            "confidence": self.confidence,
            "evidence": [asdict(item) for item in self.evidence],
        }


def _manifest_path(palace_path: Path) -> Path:
    return palace_path / MANIFEST_FILENAME


def _sqlite_path(palace_path: Path) -> Path:
    return palace_path / CHROMA_SQLITE_FILENAME


def _classify_manifest_line(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip().lower()
    if normalized == "chromadb-0.6.x":
        return CLASS_CHROMA_0_6
    if normalized in {"chromadb-1.x", "chromadb-1"}:
        return CLASS_CHROMA_1_X
    if normalized.startswith("chromadb-1."):
        return CLASS_CHROMA_1_X
    return None


def _classify_version_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if _CHROMA_0_6_VERSION_RE.fullmatch(normalized):
        return CLASS_CHROMA_0_6
    if _CHROMA_1_X_VERSION_RE.fullmatch(normalized):
        return CLASS_CHROMA_1_X
    return None


def _detect_from_manifest(palace_path: Path) -> DetectionResult | None:
    manifest_path = _manifest_path(palace_path)
    if not manifest_path.exists():
        return None

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return DetectionResult(
            palace_path=str(palace_path),
            classification=CLASS_UNKNOWN,
            confidence="low",
            evidence=[
                DetectionEvidence(
                    source="manifest",
                    detail=f"{manifest_path.name} is present but is not a JSON object",
                )
            ],
        )

    compatibility_class = _classify_manifest_line(data.get("compatibility_line"))
    version_class = _classify_version_string(data.get("chromadb_version"))

    if compatibility_class and version_class and compatibility_class != version_class:
        return DetectionResult(
            palace_path=str(palace_path),
            classification=CLASS_UNKNOWN,
            confidence="low",
            evidence=[
                DetectionEvidence(
                    source="manifest",
                    detail=(
                        "manifest fields conflict: "
                        f"compatibility_line={data.get('compatibility_line')!r}, "
                        f"chromadb_version={data.get('chromadb_version')!r}"
                    ),
                )
            ],
        )

    classification = compatibility_class or version_class
    if classification is None:
        return None

    if compatibility_class is not None:
        detail = f"compatibility_line={data.get('compatibility_line')!r}"
    else:
        detail = f"chromadb_version={data.get('chromadb_version')!r}"

    return DetectionResult(
        palace_path=str(palace_path),
        classification=classification,
        confidence="high",
        evidence=[DetectionEvidence(source="manifest", detail=detail)],
    )


def _detect_from_structure(palace_path: Path) -> DetectionResult:
    sqlite_path = _sqlite_path(palace_path)
    if not sqlite_path.exists():
        return DetectionResult(
            palace_path=str(palace_path),
            classification=CLASS_UNKNOWN,
            confidence="low",
            evidence=[
                DetectionEvidence(
                    source="structure",
                    detail=f"{CHROMA_SQLITE_FILENAME} is missing",
                )
            ],
        )

    try:
        conn = sqlite3.connect(str(sqlite_path))
    except sqlite3.Error as exc:
        return DetectionResult(
            palace_path=str(palace_path),
            classification=CLASS_UNKNOWN,
            confidence="low",
            evidence=[
                DetectionEvidence(
                    source="structure",
                    detail=f"could not open {CHROMA_SQLITE_FILENAME}: {exc}",
                )
            ],
        )

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT config_json_str FROM collections")
        rows = cursor.fetchall()
    except sqlite3.Error as exc:
        return DetectionResult(
            palace_path=str(palace_path),
            classification=CLASS_UNKNOWN,
            confidence="low",
            evidence=[
                DetectionEvidence(
                    source="structure",
                    detail=f"could not read collections.config_json_str: {exc}",
                )
            ],
        )
    finally:
        conn.close()

    if not rows:
        return DetectionResult(
            palace_path=str(palace_path),
            classification=CLASS_UNKNOWN,
            confidence="low",
            evidence=[
                DetectionEvidence(
                    source="structure",
                    detail="collections table is present but empty",
                )
            ],
        )

    typed_count = 0
    untyped_count = 0

    for (raw_value,) in rows:
        payload = raw_value or "{}"
        try:
            config = json.loads(payload)
        except json.JSONDecodeError:
            return DetectionResult(
                palace_path=str(palace_path),
                classification=CLASS_UNKNOWN,
                confidence="low",
                evidence=[
                    DetectionEvidence(
                        source="structure",
                        detail="at least one collections.config_json_str value is invalid JSON",
                    )
                ],
            )

        if not isinstance(config, dict):
            return DetectionResult(
                palace_path=str(palace_path),
                classification=CLASS_UNKNOWN,
                confidence="low",
                evidence=[
                    DetectionEvidence(
                        source="structure",
                        detail="at least one collections.config_json_str value is not a JSON object",
                    )
                ],
            )

        if config.get("_type") == "CollectionConfigurationInternal":
            typed_count += 1
        else:
            untyped_count += 1

    if typed_count == len(rows):
        return DetectionResult(
            palace_path=str(palace_path),
            classification=CLASS_CHROMA_0_6,
            confidence="medium",
            evidence=[
                DetectionEvidence(
                    source="structure",
                    detail=(
                        "every collections.config_json_str entry contains "
                        "_type='CollectionConfigurationInternal'"
                    ),
                )
            ],
        )

    if untyped_count == len(rows):
        return DetectionResult(
            palace_path=str(palace_path),
            classification=CLASS_UNKNOWN,
            confidence="low",
            evidence=[
                DetectionEvidence(
                    source="structure",
                    detail=(
                        "all collections.config_json_str entries are untyped; "
                        "this is ambiguous and not strong enough to distinguish "
                        "chroma_1_x from older incompatible storage"
                    ),
                )
            ],
        )

    return DetectionResult(
        palace_path=str(palace_path),
        classification=CLASS_UNKNOWN,
        confidence="low",
        evidence=[
            DetectionEvidence(
                source="structure",
                detail=(
                    "collections.config_json_str contains a mix of typed and untyped "
                    "entries; the storage line is ambiguous"
                ),
            )
        ],
    )


def detect_palace_format(palace_path: str | Path) -> DetectionResult:
    path = Path(palace_path).expanduser().resolve()

    manifest_result = _detect_from_manifest(path)
    if manifest_result is not None:
        return manifest_result

    return _detect_from_structure(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Detect the storage/version line of a MemPalace palace without opening it "
            "through ChromaDB."
        )
    )
    parser.add_argument("palace_path", help="Path to the palace directory to inspect")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    args = parser.parse_args()

    result = detect_palace_format(args.palace_path)
    json.dump(result.to_json_dict(), sys.stdout, indent=2 if args.pretty else None)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
