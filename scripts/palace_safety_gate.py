#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from palace_format_detector import (
    CHROMA_SQLITE_FILENAME,
    CLASS_CHROMA_0_6,
    CLASS_CHROMA_1_X,
    CLASS_UNKNOWN,
    DetectionEvidence,
    detect_palace_format,
)
from palace_legacy_repair import evaluate_legacy_repair_eligibility

Action = Literal["read", "write", "create", "repair"]


@dataclass(frozen=True)
class SafetyGateResult:
    palace_path: str
    action: Action
    allowed: bool
    classification: str
    confidence: str
    evidence: list[DetectionEvidence]
    message: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "palace_path": self.palace_path,
            "action": self.action,
            "allowed": self.allowed,
            "classification": self.classification,
            "confidence": self.confidence,
            "evidence": [asdict(item) for item in self.evidence],
            "message": self.message,
        }


def _block_message(action: Action, classification: str, palace_path: Path, detail: str) -> str:
    action_word = {
        "read": "read from",
        "write": "write to",
        "create": "reinitialize",
        "repair": "repair",
    }[action]

    if classification == CLASS_CHROMA_1_X:
        return (
            f"Refusing to {action_word} palace at {palace_path}: detected format {classification}. "
            "This stable bridge only opens chroma_0_6 palaces. "
            "Use a matching 1.x environment instead."
        )

    return (
        f"Refusing to {action_word} palace at {palace_path}: detected format is unknown. "
        f"{detail}. Inspect it first with: python3 scripts/palace_format_detector.py {palace_path} --pretty"
    )


def _legacy_repair_hint(palace_path: Path) -> str:
    return (
        "If this is a legacy palace storing an untyped config_json_str ({}), verify the narrow "
        f"repair contract with: python3 scripts/palace_legacy_repair.py {palace_path} "
        f"then apply it with: python3 scripts/palace_legacy_repair.py {palace_path} --apply"
    )


def evaluate_palace_safety(palace_path: str | Path, action: Action) -> SafetyGateResult:
    path = Path(palace_path).expanduser().resolve()
    sqlite_path = path / CHROMA_SQLITE_FILENAME

    if not sqlite_path.exists():
        return SafetyGateResult(
            palace_path=str(path),
            action=action,
            allowed=True,
            classification=CLASS_UNKNOWN,
            confidence="low",
            evidence=[
                DetectionEvidence(
                    source="structure",
                    detail=f"{CHROMA_SQLITE_FILENAME} is missing",
                )
            ],
            message=f"No existing palace database detected at {path}.",
        )

    detection = detect_palace_format(path)
    if detection.classification == CLASS_CHROMA_0_6:
        return SafetyGateResult(
            palace_path=detection.palace_path,
            action=action,
            allowed=True,
            classification=detection.classification,
            confidence=detection.confidence,
            evidence=detection.evidence,
            message="Palace format is safe for the stable chroma_0_6 path.",
        )

    # The format is not positively identified. A dedicated `repair` action may
    # still proceed, but only when the strict narrow legacy preflight passes.
    # read/write remain blocked: an untyped config alone is not proof.
    if action == "repair":
        eligibility = evaluate_legacy_repair_eligibility(path)
        if eligibility.eligible:
            return SafetyGateResult(
                palace_path=detection.palace_path,
                action=action,
                allowed=True,
                classification=detection.classification,
                confidence="medium",
                evidence=detection.evidence,
                message=(
                    "Palace is not typed, but it matches the narrow legacy repair contract "
                    "(untyped {}) — the dedicated repair is authorised."
                ),
            )

        failed = eligibility.failed_invariants()
        failed_detail = "; ".join(f"{item.name}: {item.detail}" for item in failed) or "no invariant evidence"
        return SafetyGateResult(
            palace_path=detection.palace_path,
            action=action,
            allowed=False,
            classification=detection.classification,
            confidence=detection.confidence,
            evidence=detection.evidence,
            message=(
                f"Refusing to repair palace at {path}: detected format is {detection.classification} and it "
                f"does not match the narrow legacy repair contract. {failed_detail}. "
                f"{_legacy_repair_hint(path)}"
            ),
        )

    primary_detail = detection.evidence[0].detail if detection.evidence else "No decisive evidence found"
    message = _block_message(action, detection.classification, path, primary_detail)
    if detection.classification != CLASS_CHROMA_1_X:
        message = f"{message}. {_legacy_repair_hint(path)}"

    return SafetyGateResult(
        palace_path=detection.palace_path,
        action=action,
        allowed=False,
        classification=detection.classification,
        confidence=detection.confidence,
        evidence=detection.evidence,
        message=message,
    )


def _default_palace_path() -> str:
    env_path = os.environ.get("MEMPALACE_PALACE_PATH") or os.environ.get("MEMPAL_PALACE_PATH")
    if env_path:
        return env_path
    return "~/.mempalace/palace"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Block unsafe stable-branch palace operations based on detected storage format."
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=("read", "write", "create", "repair"),
        help="Operation you intend to perform on the palace",
    )
    parser.add_argument(
        "palace_path",
        nargs="?",
        default=_default_palace_path(),
        help="Path to the palace directory to inspect",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    args = parser.parse_args()

    result = evaluate_palace_safety(args.palace_path, args.action)
    if args.json:
        json.dump(result.to_json_dict(), sys.stdout, indent=2)
        print()
    elif result.allowed:
        print(f"[OK]    {result.message}")
    else:
        print(f"[ERROR] {result.message}", file=sys.stderr)

    return 0 if result.allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
