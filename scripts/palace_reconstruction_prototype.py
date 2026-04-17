#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from palace_format_detector import CLASS_CHROMA_0_6, detect_palace_format

EXPORT_MANIFEST_FILENAME = "reconstruction-export-manifest.json"
DRAWERS_FILENAME = "drawers.jsonl"
TARGET_MANIFEST_FILENAME = "reconstruction-target-manifest.json"
RETRIEVAL_QUERIES_FILENAME = "reconstruction-retrieval-queries.json"
USAGE_SCENARIOS_FILENAME = "reconstruction-usage-scenarios.json"
BUNDLE_TYPE = "mempalace_reconstruction_bundle"
COLLECTION_NAME = "mempalace_drawers"
DEFAULT_COLLECTION_METADATA = {"hnsw:space": "cosine"}
EXPORT_FORMAT_VERSION = 1
TARGET_FORMAT_VERSION = 1
RETRIEVAL_FORMAT_VERSION = 1
USAGE_FORMAT_VERSION = 1
SAMPLE_ID_COUNT = 10
DIAGNOSTIC_PREVIEW_COUNT = 5
CONTENT_LENGTH_BUCKETS = (
    ("0", 0, 0),
    ("1-31", 1, 31),
    ("32-127", 32, 127),
    ("128-511", 128, 511),
    ("512+", 512, None),
)
RETRIEVAL_QUERY_COUNT = 5
RETRIEVAL_QUERY_WORD_LIMIT = 8
RETRIEVAL_QUERY_CHAR_LIMIT = 80
RETRIEVAL_TOP_K = 5
RETRIEVAL_COUNT_TOLERANCE = 1
RETRIEVAL_MIN_OVERLAP_RATIO = 0.4
USAGE_TOP_K = 5
USAGE_COUNT_TOLERANCE = 1
USAGE_MIN_OVERLAP_RATIO = 0.4
USAGE_ACCEPTABLE = "acceptable"
USAGE_DEGRADED = "degraded"
USAGE_UNUSABLE = "unusable"
MCP_PROTOCOL_VERSION = "2025-11-25"
MCP_REQUEST_TIMEOUT_SECONDS = 10.0
MCP_STARTUP_GRACE_SECONDS = 1.0
VALIDATION_DEBUG_FILENAME = "reconstruction-validation-debug.json"
RETRIEVAL_DEBUG_FILENAME = "reconstruction-retrieval-debug.json"
USAGE_DEBUG_FILENAME = "reconstruction-usage-debug.json"
MCP_RUNTIME_DEBUG_FILENAME = "reconstruction-mcp-runtime-debug.json"


class ReconstructionCliError(RuntimeError):
    def __init__(
        self,
        *,
        stage: str,
        category: str,
        summary: str,
        details: list[str] | None = None,
        suggested_action: str | None = None,
        where_to_look: list[str] | None = None,
    ) -> None:
        super().__init__(summary)
        self.stage = stage
        self.category = category
        self.summary = summary
        self.details = details or []
        self.suggested_action = suggested_action
        self.where_to_look = where_to_look or []

    def __str__(self) -> str:
        if not self.details:
            return self.summary
        return f"{self.summary}: {'; '.join(self.details)}"


def _iso_timestamp_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_package_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _source_db_path(source_palace: Path) -> Path:
    return source_palace / "chroma.sqlite3"


def _resolve_uv_path() -> str | None:
    uv_path = shutil.which("uv")
    if uv_path:
        return uv_path

    home = Path.home()
    for candidate in (home / ".cargo/bin/uv", home / ".local/bin/uv"):
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)

    return None


def _normalize_sqlite_metadata_value(row: sqlite3.Row) -> Any:
    if row["string_value"] is not None:
        return row["string_value"]
    if row["int_value"] is not None:
        return row["int_value"]
    if row["float_value"] is not None:
        return row["float_value"]
    if row["bool_value"] is not None:
        return bool(row["bool_value"])
    return None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _preview_items(values: list[Any], *, limit: int = DIAGNOSTIC_PREVIEW_COUNT) -> str:
    if not values:
        return "none"

    preview = ", ".join(str(value) for value in values[:limit])
    remaining = len(values) - limit
    if remaining > 0:
        return f"{preview}, ... (+{remaining} more)"
    return preview


def _raise_cli_error(
    *,
    stage: str,
    category: str,
    summary: str,
    details: list[str] | None = None,
    suggested_action: str | None = None,
    where_to_look: list[str] | None = None,
) -> None:
    raise ReconstructionCliError(
        stage=stage,
        category=category,
        summary=summary,
        details=details,
        suggested_action=suggested_action,
        where_to_look=where_to_look,
    )


def _print_cli_error(exc: ReconstructionCliError) -> None:
    print(f"[ERROR] {exc.stage.capitalize()} failed: {exc.summary}", file=sys.stderr)
    print(f"[INFO]  Category: {exc.category}", file=sys.stderr)
    if exc.details:
        print("[INFO]  Details:", file=sys.stderr)
        for detail in exc.details:
            print(f"[INFO]    - {detail}", file=sys.stderr)
    if exc.where_to_look:
        print("[INFO]  Where to look:", file=sys.stderr)
        for location in exc.where_to_look:
            print(f"[INFO]    - {location}", file=sys.stderr)
    if exc.suggested_action:
        print(f"[INFO]  Suggested action: {exc.suggested_action}", file=sys.stderr)


def _write_debug_artifact(path: Path, payload: dict[str, Any]) -> str | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        return str(path)
    except OSError as exc:
        print(f"[WARN]  Could not write debug artifact {path}: {exc}", file=sys.stderr)
        return None


def _print_error_groups(
    title: str,
    error_groups: list[dict[str, Any]],
    *,
    debug_artifact_path: str | None = None,
) -> None:
    print(f"[INFO]  {title}:", file=sys.stderr)
    for group in error_groups:
        print(f"[INFO]    {group['category'].capitalize()}:", file=sys.stderr)
        for item in group.get("items", []):
            print(f"[INFO]      - {item}", file=sys.stderr)
        for location in group.get("where_to_look", []):
            print(f"[INFO]      Where to look: {location}", file=sys.stderr)
        if group.get("suggested_action"):
            print(f"[INFO]      Suggested action: {group['suggested_action']}", file=sys.stderr)
    if debug_artifact_path:
        print(f"[INFO]  Debug artifact: {debug_artifact_path}", file=sys.stderr)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return round(numerator / denominator, 3)


def _length_profile(lengths: list[int]) -> dict[str, Any]:
    buckets = {label: 0 for label, _, _ in CONTENT_LENGTH_BUCKETS}
    for length in lengths:
        for label, lower, upper in CONTENT_LENGTH_BUCKETS:
            if upper is None and length >= lower:
                buckets[label] += 1
                break
            if upper is not None and lower <= length <= upper:
                buckets[label] += 1
                break

    return {
        "count": len(lengths),
        "total_chars": sum(lengths),
        "min_chars": min(lengths) if lengths else 0,
        "max_chars": max(lengths) if lengths else 0,
        "buckets": buckets,
    }


def _normalize_metadata(metadata: Any) -> tuple[dict[str, Any], list[str]]:
    if metadata is None:
        return {}, []

    if not isinstance(metadata, dict):
        return {}, [f"metadata must be an object, got {type(metadata).__name__}"]

    normalized: dict[str, Any] = {}
    issues: list[str] = []
    for key, value in metadata.items():
        if not isinstance(key, str):
            issues.append(f"metadata key must be a string, got {type(key).__name__}")
            continue
        if isinstance(value, bool):
            normalized[key] = value
        elif isinstance(value, (str, int, float)):
            normalized[key] = value
        else:
            issues.append(f"metadata[{key!r}] has unsupported type {type(value).__name__}")

    return normalized, issues


def _normalize_text_whitespace(value: str) -> str:
    return " ".join(value.split())


def _make_query_text(document: str) -> str | None:
    normalized = _normalize_text_whitespace(document)
    if not normalized:
        return None

    words = normalized.split(" ")
    query = " ".join(words[:RETRIEVAL_QUERY_WORD_LIMIT]).strip()
    if not query:
        return None
    if len(query) > RETRIEVAL_QUERY_CHAR_LIMIT:
        query = query[:RETRIEVAL_QUERY_CHAR_LIMIT].rstrip()
    return query


def _is_safe_bundle_relative_path(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def _validate_drawer_record(drawer: Any, *, line_number: int) -> dict[str, Any]:
    if not isinstance(drawer, dict):
        raise RuntimeError(f"Export bundle contains a non-object drawer on line {line_number}")

    allowed_keys = {"id", "document", "metadata"}
    unknown_keys = sorted(set(drawer) - allowed_keys)
    if unknown_keys:
        raise RuntimeError(
            f"Export bundle drawer on line {line_number} contains unknown fields: {', '.join(unknown_keys)}"
        )

    for required_field in ("id", "document", "metadata"):
        if required_field not in drawer:
            raise RuntimeError(
                f"Export bundle drawer on line {line_number} is missing required field {required_field}"
            )

    return drawer


def _normalize_bundle_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    format_version = manifest.get("format_version")
    if not isinstance(format_version, int) or format_version <= 0:
        raise RuntimeError("Export manifest must declare a positive integer format_version")

    normalized = dict(manifest)
    bundle_type = normalized.get("bundle_type", BUNDLE_TYPE)
    if bundle_type != BUNDLE_TYPE:
        raise RuntimeError(f"Unsupported export bundle type: {bundle_type}")
    normalized["bundle_type"] = bundle_type

    created_at = normalized.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip():
        raise RuntimeError("Export manifest must declare created_at")

    files = normalized.get("files")
    if files is None:
        files = {
            "drawers": DRAWERS_FILENAME,
            "retrieval_queries": RETRIEVAL_QUERIES_FILENAME,
            "usage_scenarios": USAGE_SCENARIOS_FILENAME,
        }
    if not isinstance(files, dict):
        raise RuntimeError("Export manifest files must be a JSON object")
    if "usage_scenarios" not in files:
        files["usage_scenarios"] = USAGE_SCENARIOS_FILENAME
    for required_file in ("drawers", "retrieval_queries", "usage_scenarios"):
        file_value = files.get(required_file)
        if not isinstance(file_value, str) or not _is_safe_bundle_relative_path(file_value):
            raise RuntimeError(f"Export manifest files.{required_file} must be a safe relative bundle path")
    normalized["files"] = files

    collection = normalized.get("collection")
    if collection is None:
        collection = {"name": COLLECTION_NAME, "metadata": DEFAULT_COLLECTION_METADATA}
    if not isinstance(collection, dict):
        raise RuntimeError("Export manifest collection must be a JSON object")
    collection_name = collection.get("name")
    if not isinstance(collection_name, str) or not collection_name.strip():
        raise RuntimeError("Export manifest collection.name must be a non-empty string")
    collection_metadata = collection.get("metadata", DEFAULT_COLLECTION_METADATA)
    normalized_metadata, metadata_issues = _normalize_metadata(collection_metadata)
    if metadata_issues:
        raise RuntimeError("Export manifest collection.metadata is invalid: " + "; ".join(metadata_issues))
    normalized["collection"] = {
        "name": collection_name,
        "metadata": normalized_metadata,
    }

    source = normalized.get("source")
    if not isinstance(source, dict):
        raise RuntimeError("Export manifest source must be a JSON object")
    for required_field in ("palace_path", "sqlite_path", "detected_format", "detection_confidence"):
        value = source.get(required_field)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"Export manifest source.{required_field} must be a non-empty string")

    summary = normalized.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("Export manifest summary must be a JSON object")
    if not isinstance(summary.get("drawer_count"), int) or summary["drawer_count"] < 0:
        raise RuntimeError("Export manifest summary.drawer_count must be a non-negative integer")
    if not isinstance(summary.get("sample_ids"), list):
        raise RuntimeError("Export manifest summary.sample_ids must be a list")
    if not isinstance(summary.get("metadata_keys"), list):
        raise RuntimeError("Export manifest summary.metadata_keys must be a list")
    if not isinstance(summary.get("wing_room_counts"), dict):
        raise RuntimeError("Export manifest summary.wing_room_counts must be an object")

    retrieval_validation = normalized.get("retrieval_validation")
    retrieval_validation_defaulted = retrieval_validation is None
    if retrieval_validation is None:
        retrieval_validation = {
            "queries_file": files["retrieval_queries"],
            "query_count": 0,
            "top_k": RETRIEVAL_TOP_K,
        }
    if not isinstance(retrieval_validation, dict):
        raise RuntimeError("Export manifest retrieval_validation must be a JSON object")
    queries_file = retrieval_validation.get("queries_file", files["retrieval_queries"])
    if not isinstance(queries_file, str) or not _is_safe_bundle_relative_path(queries_file):
        raise RuntimeError("Export manifest retrieval_validation.queries_file must be a safe relative bundle path")
    query_count = retrieval_validation.get("query_count")
    if not isinstance(query_count, int) or query_count < 0:
        raise RuntimeError("Export manifest retrieval_validation.query_count must be a non-negative integer")
    top_k = retrieval_validation.get("top_k")
    if not isinstance(top_k, int) or top_k <= 0:
        raise RuntimeError("Export manifest retrieval_validation.top_k must be a positive integer")
    normalized["retrieval_validation"] = {
        "queries_file": queries_file,
        "query_count": query_count,
        "top_k": top_k,
        "legacy_defaulted": retrieval_validation_defaulted,
    }

    usage_validation = normalized.get("usage_validation")
    usage_validation_defaulted = usage_validation is None
    if usage_validation is None:
        usage_validation = {
            "scenarios_file": files["usage_scenarios"],
            "scenario_count": 0,
            "top_k": USAGE_TOP_K,
        }
    if not isinstance(usage_validation, dict):
        raise RuntimeError("Export manifest usage_validation must be a JSON object")
    scenarios_file = usage_validation.get("scenarios_file", files["usage_scenarios"])
    if not isinstance(scenarios_file, str) or not _is_safe_bundle_relative_path(scenarios_file):
        raise RuntimeError("Export manifest usage_validation.scenarios_file must be a safe relative bundle path")
    scenario_count = usage_validation.get("scenario_count")
    if not isinstance(scenario_count, int) or scenario_count < 0:
        raise RuntimeError("Export manifest usage_validation.scenario_count must be a non-negative integer")
    usage_top_k = usage_validation.get("top_k")
    if not isinstance(usage_top_k, int) or usage_top_k <= 0:
        raise RuntimeError("Export manifest usage_validation.top_k must be a positive integer")
    normalized["usage_validation"] = {
        "scenarios_file": scenarios_file,
        "scenario_count": scenario_count,
        "top_k": usage_top_k,
        "legacy_defaulted": usage_validation_defaulted,
    }

    warnings = normalized.get("warnings", [])
    if not isinstance(warnings, list):
        raise RuntimeError("Export manifest warnings must be a list when present")

    return normalized


def _analyze_drawers(drawers: list[dict[str, Any]]) -> dict[str, Any]:
    wing_room_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    metadata_keys: set[str] = set()
    id_counts: dict[str, int] = {}
    blank_id_records: list[dict[str, Any]] = []
    non_string_document_ids: list[str] = []
    empty_document_ids: list[str] = []
    metadata_structure_issues: dict[str, list[str]] = {}
    document_hashes: dict[str, str] = {}
    document_lengths: dict[str, int] = {}
    documents_by_id: dict[str, str] = {}
    metadata_hashes: dict[str, str] = {}
    metadata_by_id: dict[str, dict[str, Any]] = {}
    valid_ids_in_order: list[str] = []

    for index, drawer in enumerate(drawers):
        drawer_id_raw = drawer.get("id")
        drawer_id = drawer_id_raw if isinstance(drawer_id_raw, str) and drawer_id_raw.strip() else None
        if drawer_id is None:
            blank_id_records.append({"index": index, "value": drawer_id_raw})
        else:
            valid_ids_in_order.append(drawer_id)
            id_counts[drawer_id] = id_counts.get(drawer_id, 0) + 1

        document = drawer.get("document")
        if drawer_id is not None:
            if not isinstance(document, str):
                non_string_document_ids.append(drawer_id)
            else:
                documents_by_id[drawer_id] = document
                document_lengths[drawer_id] = len(document)
                document_hashes[drawer_id] = _sha256_text(document)
                if not document.strip():
                    empty_document_ids.append(drawer_id)

        normalized_metadata, metadata_issues = _normalize_metadata(drawer.get("metadata", {}))
        wing = str(normalized_metadata.get("wing", "?"))
        room = str(normalized_metadata.get("room", "?"))
        wing_room_counts[wing][room] += 1
        metadata_keys.update(normalized_metadata.keys())

        if drawer_id is not None:
            if metadata_issues:
                metadata_structure_issues[drawer_id] = metadata_issues
            metadata_by_id[drawer_id] = normalized_metadata
            metadata_hashes[drawer_id] = _sha256_text(_canonical_json(normalized_metadata))

    duplicate_ids = sorted([drawer_id for drawer_id, count in id_counts.items() if count > 1])
    for drawer_id in duplicate_ids:
        document_hashes.pop(drawer_id, None)
        document_lengths.pop(drawer_id, None)
        documents_by_id.pop(drawer_id, None)
        metadata_hashes.pop(drawer_id, None)
        metadata_by_id.pop(drawer_id, None)

    length_values = list(document_lengths.values())
    return {
        "drawer_count": len(drawers),
        "ids": sorted(id_counts),
        "sample_ids": valid_ids_in_order[:SAMPLE_ID_COUNT],
        "metadata_keys": sorted(metadata_keys),
        "wing_room_counts": {wing: dict(sorted(rooms.items())) for wing, rooms in sorted(wing_room_counts.items())},
        "id_integrity": {
            "unique_id_count": len(id_counts),
            "duplicate_ids": duplicate_ids,
            "blank_id_records": blank_id_records,
        },
        "content_integrity": {
            "non_string_document_ids": sorted(non_string_document_ids),
            "empty_document_ids": sorted(empty_document_ids),
            "length_profile": _length_profile(length_values),
        },
        "metadata_integrity": {
            "structural_issue_ids": sorted(metadata_structure_issues),
            "structural_issues": metadata_structure_issues,
        },
        "indexes": {
            "document_hashes": document_hashes,
            "document_lengths": document_lengths,
            "documents_by_id": documents_by_id,
            "metadata_hashes": metadata_hashes,
            "metadata_by_id": metadata_by_id,
        },
    }


def _build_query_candidates(drawers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    analysis = _analyze_drawers(drawers)
    metadata_by_id = analysis["indexes"]["metadata_by_id"]
    documents_by_id = analysis["indexes"]["documents_by_id"]

    candidates: list[dict[str, Any]] = []
    for drawer_id in analysis["ids"]:
        document = documents_by_id.get(drawer_id)
        if not isinstance(document, str):
            continue
        query_text = _make_query_text(document)
        if not query_text:
            continue
        metadata = metadata_by_id.get(drawer_id, {})
        candidates.append(
            {
                "id": drawer_id,
                "query_text": query_text,
                "wing": str(metadata.get("wing", "?")),
                "room": str(metadata.get("room", "?")),
                "document": document,
                "document_preview": document[:RETRIEVAL_QUERY_CHAR_LIMIT],
            }
        )

    return candidates


def build_retrieval_query_plan(
    drawers: list[dict[str, Any]],
    *,
    max_queries: int = RETRIEVAL_QUERY_COUNT,
    top_k: int = RETRIEVAL_TOP_K,
) -> dict[str, Any]:
    candidates = _build_query_candidates(drawers)

    selected: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    used_query_texts: set[str] = set()
    seen_wing_rooms: set[tuple[str, str]] = set()

    for candidate in sorted(candidates, key=lambda item: (item["wing"], item["room"], item["id"])):
        wing_room = (candidate["wing"], candidate["room"])
        if wing_room in seen_wing_rooms or candidate["query_text"] in used_query_texts:
            continue
        selected.append({**candidate, "selection_reason": "wing_room_representative"})
        used_ids.add(candidate["id"])
        used_query_texts.add(candidate["query_text"])
        seen_wing_rooms.add(wing_room)
        if len(selected) >= max_queries:
            break

    if len(selected) < max_queries:
        for candidate in sorted(candidates, key=lambda item: item["id"]):
            if candidate["id"] in used_ids or candidate["query_text"] in used_query_texts:
                continue
            selected.append({**candidate, "selection_reason": "fill"})
            used_ids.add(candidate["id"])
            used_query_texts.add(candidate["query_text"])
            if len(selected) >= max_queries:
                break

    queries = [
        {
            "query_id": f"query-{index + 1:03d}",
            "query_text": candidate["query_text"],
            "anchor_id": candidate["id"],
            "wing": candidate["wing"],
            "room": candidate["room"],
            "document_preview": candidate["document_preview"],
            "selection_reason": candidate["selection_reason"],
        }
        for index, candidate in enumerate(selected)
    ]

    return {
        "format_version": RETRIEVAL_FORMAT_VERSION,
        "created_at": _iso_timestamp_now(),
        "top_k": top_k,
        "queries": queries,
    }


def _make_multi_step_broad_query(query_text: str) -> str:
    words = query_text.split()
    if len(words) <= 1:
        return query_text

    broad_word_count = max(1, min(4, len(words) - 1))
    return " ".join(words[:broad_word_count])


def _make_copilot_style_prompt(candidate: dict[str, Any]) -> str:
    query_text = candidate["query_text"]
    wing = candidate["wing"]
    room = candidate["room"]
    if wing != "?" or room != "?":
        return f"I need context about {query_text}. Focus on wing {wing} room {room}."
    return f"I need context about {query_text}. Summarize the most relevant stored notes."


def build_usage_scenario_plan(
    drawers: list[dict[str, Any]],
    *,
    top_k: int = USAGE_TOP_K,
) -> dict[str, Any]:
    candidates = sorted(_build_query_candidates(drawers), key=lambda item: (item["wing"], item["room"], item["id"]))
    if not candidates:
        return {
            "format_version": USAGE_FORMAT_VERSION,
            "created_at": _iso_timestamp_now(),
            "top_k": top_k,
            "scenarios": [],
        }

    scenarios: list[dict[str, Any]] = []
    simple_candidates = candidates[: min(2, len(candidates))]
    multi_candidates = candidates[: min(2, len(candidates))]
    copilot_candidate = candidates[min(2, len(candidates) - 1)]

    for index, candidate in enumerate(simple_candidates, start=1):
        scenarios.append(
            {
                "scenario_id": f"usage-{len(scenarios) + 1:03d}",
                "scenario_type": "simple_query",
                "anchor_id": candidate["id"],
                "wing": candidate["wing"],
                "room": candidate["room"],
                "document_preview": candidate["document_preview"],
                "selection_reason": f"simple_query_representative_{index}",
                "steps": [
                    {
                        "step_id": "step-001",
                        "query_text": candidate["query_text"],
                        "purpose": "simple_lookup",
                    }
                ],
            }
        )

    for index, candidate in enumerate(multi_candidates, start=1):
        broad_query = _make_multi_step_broad_query(candidate["query_text"])
        scenarios.append(
            {
                "scenario_id": f"usage-{len(scenarios) + 1:03d}",
                "scenario_type": "multi_step_retrieval",
                "anchor_id": candidate["id"],
                "wing": candidate["wing"],
                "room": candidate["room"],
                "document_preview": candidate["document_preview"],
                "selection_reason": f"multi_step_representative_{index}",
                "steps": [
                    {
                        "step_id": "step-001",
                        "query_text": broad_query,
                        "purpose": "initial_lookup",
                    },
                    {
                        "step_id": "step-002",
                        "query_text": candidate["query_text"],
                        "purpose": "refined_lookup",
                    },
                ],
            }
        )

    scenarios.append(
        {
            "scenario_id": f"usage-{len(scenarios) + 1:03d}",
            "scenario_type": "copilot_prompt",
            "anchor_id": copilot_candidate["id"],
            "wing": copilot_candidate["wing"],
            "room": copilot_candidate["room"],
            "document_preview": copilot_candidate["document_preview"],
            "selection_reason": "copilot_style_prompt",
            "steps": [
                {
                    "step_id": "step-001",
                    "query_text": _make_copilot_style_prompt(copilot_candidate),
                    "purpose": "copilot_style_lookup",
                }
            ],
        }
    )

    return {
        "format_version": USAGE_FORMAT_VERSION,
        "created_at": _iso_timestamp_now(),
        "top_k": top_k,
        "scenarios": scenarios,
    }


def _source_sqlite_integrity(db_path: Path) -> dict[str, Any]:
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        _raise_cli_error(
            stage="export",
            category="structural",
            summary=f"source palace database is unreadable: {exc}",
            details=[f"sqlite path: {db_path}"],
            where_to_look=[str(db_path)],
            suggested_action="The database file may be corrupted or not a valid SQLite database. Verify the file integrity.",
        )
    try:
        embedding_row_count = conn.execute("SELECT COUNT(*) AS count FROM embeddings").fetchone()["count"]

        blank_id_rows = [
            {"row_id": row["row_id"], "value": row["embedding_id"]}
            for row in conn.execute(
                """
                SELECT id AS row_id, embedding_id
                FROM embeddings
                WHERE embedding_id IS NULL OR TRIM(embedding_id) = ''
                ORDER BY id
                """
            ).fetchall()
        ]

        duplicate_ids: list[dict[str, Any]] = []
        duplicate_rows = conn.execute(
            """
            SELECT embedding_id, COUNT(*) AS row_count
            FROM embeddings
            WHERE embedding_id IS NOT NULL AND TRIM(embedding_id) != ''
            GROUP BY embedding_id
            HAVING COUNT(*) > 1
            ORDER BY embedding_id
            """
        ).fetchall()
        for row in duplicate_rows:
            row_ids = [
                duplicate_row["id"]
                for duplicate_row in conn.execute(
                    "SELECT id FROM embeddings WHERE embedding_id = ? ORDER BY id", (row["embedding_id"],)
                ).fetchall()
            ]
            duplicate_ids.append(
                {
                    "id": row["embedding_id"],
                    "count": row["row_count"],
                    "row_ids": row_ids,
                }
            )

        document_row_issues = [
            {
                "row_id": row["row_id"],
                "id": row["embedding_id"],
                "document_entry_count": row["document_entry_count"],
            }
            for row in conn.execute(
                """
                SELECT e.id AS row_id,
                       e.embedding_id,
                       SUM(CASE WHEN em.key = 'chroma:document' THEN 1 ELSE 0 END) AS document_entry_count
                FROM embeddings e
                LEFT JOIN embedding_metadata em ON em.id = e.id
                GROUP BY e.id, e.embedding_id
                HAVING document_entry_count != 1
                ORDER BY e.id
                """
            ).fetchall()
        ]

        duplicate_metadata_keys = [
            {
                "row_id": row["row_id"],
                "id": row["embedding_id"],
                "key": row["key"],
                "entry_count": row["entry_count"],
            }
            for row in conn.execute(
                """
                SELECT e.id AS row_id,
                       e.embedding_id,
                       em.key,
                       COUNT(*) AS entry_count
                FROM embeddings e
                JOIN embedding_metadata em ON em.id = e.id
                WHERE em.key NOT LIKE 'chroma:%'
                GROUP BY e.id, e.embedding_id, em.key
                HAVING COUNT(*) > 1
                ORDER BY e.id, em.key
                """
            ).fetchall()
        ]

        return {
            "embedding_row_count": embedding_row_count,
            "blank_id_rows": blank_id_rows,
            "duplicate_ids": duplicate_ids,
            "document_row_issues": document_row_issues,
            "duplicate_metadata_keys": duplicate_metadata_keys,
            "valid": not any([blank_id_rows, duplicate_ids, document_row_issues, duplicate_metadata_keys]),
        }
    except sqlite3.Error as exc:
        _raise_cli_error(
            stage="export",
            category="structural",
            summary=f"source palace database query failed: {exc}",
            details=[f"sqlite path: {db_path}"],
            where_to_look=[str(db_path)],
            suggested_action="The database may have an unexpected schema or be corrupted. Inspect the SQLite file manually.",
        )
    finally:
        conn.close()


def _bundle_integrity_issues(manifest: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    id_integrity = analysis["id_integrity"]
    content_integrity = analysis["content_integrity"]
    metadata_integrity = analysis["metadata_integrity"]

    if id_integrity["blank_id_records"]:
        issues.append(
            "blank drawer ids in export bundle at indexes "
            f"{_preview_items([record['index'] for record in id_integrity['blank_id_records']])}"
        )
    if id_integrity["duplicate_ids"]:
        issues.append(f"duplicate drawer ids in export bundle: {_preview_items(id_integrity['duplicate_ids'])}")
    if content_integrity["non_string_document_ids"]:
        issues.append(
            "non-string documents in export bundle: " f"{_preview_items(content_integrity['non_string_document_ids'])}"
        )
    if content_integrity["empty_document_ids"]:
        issues.append(f"empty documents in export bundle: {_preview_items(content_integrity['empty_document_ids'])}")
    if metadata_integrity["structural_issue_ids"]:
        issues.append(
            "metadata structural issues in export bundle: "
            f"{_preview_items(metadata_integrity['structural_issue_ids'])}"
        )

    manifest_summary = manifest.get("summary", {})
    expected_drawer_count = manifest_summary.get("drawer_count")
    if isinstance(expected_drawer_count, int) and expected_drawer_count != analysis["drawer_count"]:
        issues.append(
            f"export manifest drawer_count={expected_drawer_count} does not match bundle count={analysis['drawer_count']}"
        )

    expected_wing_room_counts = manifest_summary.get("wing_room_counts")
    if isinstance(expected_wing_room_counts, dict) and expected_wing_room_counts != analysis["wing_room_counts"]:
        issues.append("export manifest wing_room_counts do not match bundle contents")

    expected_sample_ids = manifest_summary.get("sample_ids")
    if isinstance(expected_sample_ids, list) and expected_sample_ids != analysis["sample_ids"]:
        issues.append("export manifest sample_ids do not match bundle contents")

    collection = manifest.get("collection", {})
    if collection.get("name") != COLLECTION_NAME:
        issues.append(
            f"export manifest collection.name={collection.get('name')} does not match supported collection {COLLECTION_NAME}"
        )

    return issues


def _fetch_collection_drawers(
    collection: Any, *, include_embeddings: bool
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    include = ["documents", "metadatas"]
    if include_embeddings:
        include.append("embeddings")

    drawers: list[dict[str, Any]] = []
    missing_embedding_ids: list[str] = []
    limit = 500
    offset = 0

    while True:
        batch = collection.get(limit=limit, offset=offset, include=include)
        ids = list(batch.get("ids", []))
        if not ids:
            break

        documents = list(batch.get("documents", []))
        metadatas = list(batch.get("metadatas", []))
        embeddings = batch.get("embeddings") if include_embeddings else None

        for index, drawer_id in enumerate(ids):
            document = documents[index] if index < len(documents) else None
            metadata = metadatas[index] if index < len(metadatas) else None
            drawers.append({"id": drawer_id, "document": document, "metadata": metadata})

            if include_embeddings:
                embedding = None if embeddings is None or index >= len(embeddings) else embeddings[index]
                if embedding is None or len(embedding) == 0:
                    missing_embedding_ids.append(drawer_id)

        offset += len(ids)
        if len(ids) < limit:
            break

    embedding_diagnostics = {
        "checked": include_embeddings,
        "accessible": include_embeddings,
        "checked_count": len(drawers) if include_embeddings else 0,
        "missing_ids": sorted(missing_embedding_ids),
        "present_count": len(drawers) - len(missing_embedding_ids) if include_embeddings else 0,
    }
    return drawers, embedding_diagnostics


def _source_export_issues(source_integrity: dict[str, Any], export_analysis: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if source_integrity["blank_id_rows"]:
        issues.append(
            "blank source ids at sqlite rows "
            f"{_preview_items([row['row_id'] for row in source_integrity['blank_id_rows']])}"
        )
    if source_integrity["duplicate_ids"]:
        issues.append(
            "duplicate source ids: " f"{_preview_items([entry['id'] for entry in source_integrity['duplicate_ids']])}"
        )
    if source_integrity["document_row_issues"]:
        issues.append(
            "invalid chroma:document entry counts at sqlite rows "
            f"{_preview_items([row['row_id'] for row in source_integrity['document_row_issues']])}"
        )
    if source_integrity["duplicate_metadata_keys"]:
        issues.append(
            "duplicate metadata keys at sqlite rows "
            f"{_preview_items([row['row_id'] for row in source_integrity['duplicate_metadata_keys']])}"
        )
    if export_analysis["drawer_count"] != source_integrity["embedding_row_count"]:
        issues.append(
            "exported drawer count does not match sqlite embeddings rows "
            f"({export_analysis['drawer_count']} != {source_integrity['embedding_row_count']})"
        )
    if export_analysis["content_integrity"]["non_string_document_ids"]:
        issues.append(
            "non-string exported documents: "
            f"{_preview_items(export_analysis['content_integrity']['non_string_document_ids'])}"
        )
    if export_analysis["content_integrity"]["empty_document_ids"]:
        issues.append(
            "empty exported documents: "
            f"{_preview_items(export_analysis['content_integrity']['empty_document_ids'])}"
        )
    if export_analysis["metadata_integrity"]["structural_issue_ids"]:
        issues.append(
            "metadata structural issues in exported drawers: "
            f"{_preview_items(export_analysis['metadata_integrity']['structural_issue_ids'])}"
        )

    return issues


def extract_drawers_from_sqlite(db_path: Path) -> list[dict[str, Any]]:
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        _raise_cli_error(
            stage="export",
            category="structural",
            summary=f"source palace database is unreadable: {exc}",
            details=[f"sqlite path: {db_path}"],
            where_to_look=[str(db_path)],
            suggested_action="The database file may be corrupted or not a valid SQLite database. Verify the file integrity.",
        )
    try:
        rows = conn.execute(
            """
            SELECT e.embedding_id,
                   MAX(CASE WHEN em.key = 'chroma:document' THEN em.string_value END) AS document
            FROM embeddings e
            JOIN embedding_metadata em ON em.id = e.id
            GROUP BY e.embedding_id
            ORDER BY e.embedding_id
            """
        ).fetchall()

        drawers: list[dict[str, Any]] = []
        for row in rows:
            drawer_id = row["embedding_id"]
            document = row["document"]
            if drawer_id is None or document is None:
                continue

            meta_rows = conn.execute(
                """
                SELECT em.key, em.string_value, em.int_value, em.float_value, em.bool_value
                FROM embedding_metadata em
                JOIN embeddings e ON e.id = em.id
                WHERE e.embedding_id = ?
                  AND em.key NOT LIKE 'chroma:%'
                ORDER BY em.key
                """,
                (drawer_id,),
            ).fetchall()

            metadata: dict[str, Any] = {}
            for meta_row in meta_rows:
                key = meta_row["key"]
                value = _normalize_sqlite_metadata_value(meta_row)
                if key is not None and value is not None:
                    metadata[key] = value

            drawers.append(
                {
                    "id": drawer_id,
                    "document": document,
                    "metadata": metadata,
                }
            )

        return drawers
    except sqlite3.Error as exc:
        _raise_cli_error(
            stage="export",
            category="structural",
            summary=f"source palace database query failed: {exc}",
            details=[f"sqlite path: {db_path}"],
            where_to_look=[str(db_path)],
            suggested_action="The database may have an unexpected schema or be corrupted. Inspect the SQLite file manually.",
        )
    finally:
        conn.close()


def summarize_drawers(drawers: list[dict[str, Any]]) -> dict[str, Any]:
    analysis = _analyze_drawers(drawers)
    return {
        "drawer_count": analysis["drawer_count"],
        "sample_ids": analysis["sample_ids"],
        "metadata_keys": analysis["metadata_keys"],
        "wing_room_counts": analysis["wing_room_counts"],
        "id_integrity": {
            "unique_id_count": analysis["id_integrity"]["unique_id_count"],
            "duplicate_id_count": len(analysis["id_integrity"]["duplicate_ids"]),
            "duplicate_ids": analysis["id_integrity"]["duplicate_ids"],
            "blank_id_count": len(analysis["id_integrity"]["blank_id_records"]),
        },
        "content_integrity": {
            "non_string_document_count": len(analysis["content_integrity"]["non_string_document_ids"]),
            "empty_document_count": len(analysis["content_integrity"]["empty_document_ids"]),
            "length_profile": analysis["content_integrity"]["length_profile"],
        },
        "metadata_integrity": {
            "structural_issue_count": len(analysis["metadata_integrity"]["structural_issue_ids"]),
            "structural_issue_ids": analysis["metadata_integrity"]["structural_issue_ids"],
        },
    }


def export_drawers(source_palace: Path, export_dir: Path) -> dict[str, Any]:
    detection = detect_palace_format(source_palace)
    if detection.classification != CLASS_CHROMA_0_6:
        _raise_cli_error(
            stage="export",
            category="structural",
            summary="source palace is not classified as chroma_0_6",
            details=[f"detected classification: {detection.classification}"],
            where_to_look=[str(source_palace)],
            suggested_action="Run the prototype only against a preserved chroma_0_6 source palace or inspect format detection before retrying.",
        )

    db_path = _source_db_path(source_palace)
    if not db_path.exists():
        _raise_cli_error(
            stage="export",
            category="structural",
            summary="source palace database is missing",
            details=[f"expected sqlite path: {db_path}"],
            where_to_look=[str(source_palace)],
            suggested_action="Verify the palace path and make sure chroma.sqlite3 exists before retrying export.",
        )

    if export_dir.exists():
        _raise_cli_error(
            stage="export",
            category="structural",
            summary="output directory already exists",
            details=[f"output directory: {export_dir}"],
            where_to_look=[str(export_dir)],
            suggested_action="Choose a new empty export directory so the bundle is created deterministically.",
        )

    source_integrity = _source_sqlite_integrity(db_path)
    drawers = extract_drawers_from_sqlite(db_path)
    if not drawers:
        _raise_cli_error(
            stage="export",
            category="data integrity",
            summary="no drawers were extracted from the source palace",
            details=[f"sqlite path: {db_path}"],
            where_to_look=[str(db_path)],
            suggested_action="Inspect the source SQLite contents and confirm the embeddings and embedding_metadata tables contain MemPalace drawers.",
        )

    export_analysis = _analyze_drawers(drawers)
    export_issues = _source_export_issues(source_integrity, export_analysis)
    if export_issues:
        _raise_cli_error(
            stage="export",
            category="data integrity",
            summary="source palace failed integrity checks before bundle generation",
            details=export_issues,
            where_to_look=[str(db_path), str(source_palace / "mempalace-bridge-manifest.json")],
            suggested_action="Inspect the referenced sqlite rows or drawer ids, repair the source data, and rerun export without modifying the original palace in place.",
        )

    summary = summarize_drawers(drawers)
    retrieval_queries = build_retrieval_query_plan(drawers)
    if not retrieval_queries["queries"]:
        _raise_cli_error(
            stage="export",
            category="structural",
            summary="bundle generation could not build deterministic retrieval validation queries",
            details=[f"drawer count: {summary['drawer_count']}"],
            where_to_look=[str(db_path)],
            suggested_action="Check whether the exported documents contain usable text content and rerun export after fixing empty or malformed drawers.",
        )
    usage_scenarios = build_usage_scenario_plan(drawers)
    if not usage_scenarios["scenarios"]:
        _raise_cli_error(
            stage="export",
            category="structural",
            summary="bundle generation could not build deterministic usage scenarios",
            details=[f"drawer count: {summary['drawer_count']}"],
            where_to_look=[str(db_path)],
            suggested_action="Inspect the exported drawer documents and metadata, then retry once the source data has usable retrieval anchors.",
        )
    export_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "format_version": EXPORT_FORMAT_VERSION,
        "bundle_type": BUNDLE_TYPE,
        "created_at": _iso_timestamp_now(),
        "files": {
            "drawers": DRAWERS_FILENAME,
            "retrieval_queries": RETRIEVAL_QUERIES_FILENAME,
            "usage_scenarios": USAGE_SCENARIOS_FILENAME,
        },
        "collection": {
            "name": COLLECTION_NAME,
            "metadata": DEFAULT_COLLECTION_METADATA,
        },
        "warnings": (
            ["Source detection relied on structural hints rather than explicit manifest metadata."]
            if detection.confidence != "high"
            else []
        ),
        "source": {
            "palace_path": str(source_palace),
            "sqlite_path": str(db_path),
            "detected_format": detection.classification,
            "detection_confidence": detection.confidence,
            "detection_evidence": [e.__dict__ for e in detection.evidence],
            "chromadb_version": _load_package_version("chromadb"),
            "mempalace_version": _load_package_version("mempalace"),
            "integrity": {
                "embedding_row_count": source_integrity["embedding_row_count"],
                "blank_id_row_count": len(source_integrity["blank_id_rows"]),
                "duplicate_id_count": len(source_integrity["duplicate_ids"]),
                "document_row_issue_count": len(source_integrity["document_row_issues"]),
                "duplicate_metadata_key_count": len(source_integrity["duplicate_metadata_keys"]),
            },
        },
        "summary": summary,
        "retrieval_validation": {
            "queries_file": RETRIEVAL_QUERIES_FILENAME,
            "query_count": len(retrieval_queries["queries"]),
            "top_k": retrieval_queries["top_k"],
        },
        "usage_validation": {
            "scenarios_file": USAGE_SCENARIOS_FILENAME,
            "scenario_count": len(usage_scenarios["scenarios"]),
            "top_k": usage_scenarios["top_k"],
        },
    }

    with (export_dir / EXPORT_MANIFEST_FILENAME).open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")

    with (export_dir / DRAWERS_FILENAME).open("w", encoding="utf-8") as handle:
        for drawer in drawers:
            json.dump(drawer, handle, sort_keys=True)
            handle.write("\n")

    with (export_dir / RETRIEVAL_QUERIES_FILENAME).open("w", encoding="utf-8") as handle:
        json.dump(retrieval_queries, handle, indent=2)
        handle.write("\n")

    with (export_dir / USAGE_SCENARIOS_FILENAME).open("w", encoding="utf-8") as handle:
        json.dump(usage_scenarios, handle, indent=2)
        handle.write("\n")

    return manifest


def load_export_bundle(export_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_path = export_dir / EXPORT_MANIFEST_FILENAME
    if not manifest_path.exists():
        raise RuntimeError(f"Export bundle is incomplete at {export_dir}; expected {EXPORT_MANIFEST_FILENAME}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Export manifest is not valid JSON: {exc.msg}") from exc
    if not isinstance(manifest, dict):
        raise RuntimeError("Export manifest must be a JSON object")
    manifest = _normalize_bundle_manifest(manifest)

    drawers_path = export_dir / manifest["files"]["drawers"]
    if not drawers_path.exists():
        raise RuntimeError(f"Export bundle is incomplete at {export_dir}; expected {manifest['files']['drawers']}")

    drawers: list[dict[str, Any]] = []
    with drawers_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if line:
                try:
                    drawer = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Export bundle contains invalid JSON on line {line_number}: {exc.msg}"
                    ) from exc
                drawers.append(_validate_drawer_record(drawer, line_number=line_number))

    return manifest, drawers


def load_retrieval_query_plan(queries_path: Path) -> dict[str, Any]:
    if not queries_path.exists():
        raise RuntimeError(f"Retrieval queries file is missing at {queries_path}")

    try:
        query_plan = json.loads(queries_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Retrieval queries file is not valid JSON: {exc.msg}") from exc

    if not isinstance(query_plan, dict):
        raise RuntimeError("Retrieval queries file must be a JSON object")

    queries = query_plan.get("queries")
    if not isinstance(queries, list) or not queries:
        raise RuntimeError("Retrieval queries file must contain a non-empty queries list")

    for query in queries:
        if not isinstance(query, dict):
            raise RuntimeError("Each retrieval query entry must be a JSON object")
        for required_field in ("query_id", "query_text", "anchor_id"):
            value = query.get(required_field)
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError(f"Retrieval query is missing required field {required_field}")

    top_k = query_plan.get("top_k")
    if not isinstance(top_k, int) or top_k <= 0:
        raise RuntimeError("Retrieval queries file must declare a positive integer top_k")

    return query_plan


def load_retrieval_query_plan_from_bundle(export_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    queries_path = export_dir / manifest["retrieval_validation"]["queries_file"]
    legacy_defaulted = bool(manifest["retrieval_validation"].get("legacy_defaulted"))
    if not queries_path.exists():
        if manifest["retrieval_validation"]["query_count"] == 0:
            return {
                "format_version": RETRIEVAL_FORMAT_VERSION,
                "created_at": None,
                "top_k": manifest["retrieval_validation"]["top_k"],
                "queries": [],
            }
        raise RuntimeError(f"Retrieval queries file is missing at {queries_path}")
    query_plan = load_retrieval_query_plan(queries_path)
    if not legacy_defaulted and query_plan["top_k"] != manifest["retrieval_validation"]["top_k"]:
        raise RuntimeError("Retrieval queries top_k does not match the export manifest")
    if not legacy_defaulted and len(query_plan["queries"]) != manifest["retrieval_validation"]["query_count"]:
        raise RuntimeError("Retrieval queries count does not match the export manifest")
    return query_plan


def load_usage_scenario_plan(scenarios_path: Path) -> dict[str, Any]:
    if not scenarios_path.exists():
        raise RuntimeError(f"Usage scenarios file is missing at {scenarios_path}")

    try:
        scenario_plan = json.loads(scenarios_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Usage scenarios file is not valid JSON: {exc.msg}") from exc

    if not isinstance(scenario_plan, dict):
        raise RuntimeError("Usage scenarios file must be a JSON object")

    top_k = scenario_plan.get("top_k")
    if not isinstance(top_k, int) or top_k <= 0:
        raise RuntimeError("Usage scenarios file must declare a positive integer top_k")

    scenarios = scenario_plan.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise RuntimeError("Usage scenarios file must contain a non-empty scenarios list")

    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise RuntimeError("Each usage scenario entry must be a JSON object")
        for required_field in ("scenario_id", "scenario_type", "anchor_id"):
            value = scenario.get(required_field)
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError(f"Usage scenario is missing required field {required_field}")
        steps = scenario.get("steps")
        if not isinstance(steps, list) or not steps:
            raise RuntimeError("Usage scenario must contain a non-empty steps list")
        for step in steps:
            if not isinstance(step, dict):
                raise RuntimeError("Usage scenario steps must be JSON objects")
            for required_field in ("step_id", "query_text", "purpose"):
                value = step.get(required_field)
                if not isinstance(value, str) or not value.strip():
                    raise RuntimeError(f"Usage scenario step is missing required field {required_field}")

    return scenario_plan


def load_usage_scenario_plan_from_bundle(
    export_dir: Path,
    manifest: dict[str, Any],
    drawers: list[dict[str, Any]],
) -> dict[str, Any]:
    scenarios_path = export_dir / manifest["usage_validation"]["scenarios_file"]
    legacy_defaulted = bool(manifest["usage_validation"].get("legacy_defaulted"))
    if not scenarios_path.exists():
        if legacy_defaulted:
            scenario_plan = build_usage_scenario_plan(drawers, top_k=manifest["usage_validation"]["top_k"])
            if not scenario_plan["scenarios"]:
                raise RuntimeError("Usage scenarios file is missing and could not be reconstructed from the bundle")
            return scenario_plan
        raise RuntimeError(f"Usage scenarios file is missing at {scenarios_path}")

    scenario_plan = load_usage_scenario_plan(scenarios_path)
    if not legacy_defaulted and scenario_plan["top_k"] != manifest["usage_validation"]["top_k"]:
        raise RuntimeError("Usage scenarios top_k does not match the export manifest")
    if not legacy_defaulted and len(scenario_plan["scenarios"]) != manifest["usage_validation"]["scenario_count"]:
        raise RuntimeError("Usage scenarios count does not match the export manifest")
    return scenario_plan


class _McpStdioSession:
    def __init__(
        self,
        *,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        startup_grace_seconds: float,
        request_timeout_seconds: float,
    ) -> None:
        self.command = command
        self.cwd = cwd
        self.env = env
        self.startup_grace_seconds = startup_grace_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._stdout_queue: queue.Queue[str | None] = queue.Queue()
        self._stderr_queue: queue.Queue[str | None] = queue.Queue()
        self._stderr_lines: list[str] = []
        self._stdout_thread = threading.Thread(
            target=self._stream_to_queue, args=(self.process.stdout, self._stdout_queue), daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._stream_to_queue, args=(self.process.stderr, self._stderr_queue), daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        time.sleep(self.startup_grace_seconds)

    @staticmethod
    def _stream_to_queue(stream: Any, output_queue: queue.Queue[str | None]) -> None:
        try:
            for line in iter(stream.readline, ""):
                output_queue.put(line.rstrip("\n"))
        finally:
            output_queue.put(None)

    def _drain_stderr(self) -> None:
        while True:
            try:
                line = self._stderr_queue.get_nowait()
            except queue.Empty:
                return
            if line is not None:
                self._stderr_lines.append(line)

    def stderr_preview(self) -> list[str]:
        self._drain_stderr()
        return self._stderr_lines[-DIAGNOSTIC_PREVIEW_COUNT:]

    def _raise_if_exited(self, *, context: str) -> None:
        self._drain_stderr()
        if self.process.poll() is not None:
            stderr_preview = _preview_items(self._stderr_lines)
            raise RuntimeError(
                f"MCP server exited during {context} with code {self.process.returncode}. " f"stderr: {stderr_preview}"
            )

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._raise_if_exited(context="request setup")
        if self.process.stdin is None:
            raise RuntimeError("MCP server stdin is not available")
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

        deadline = time.time() + self.request_timeout_seconds
        while time.time() < deadline:
            self._drain_stderr()
            self._raise_if_exited(context=f"request {payload.get('method')}")
            timeout = max(0.05, min(0.25, deadline - time.time()))
            try:
                line = self._stdout_queue.get(timeout=timeout)
            except queue.Empty:
                continue
            if line is None:
                continue
            if not line.strip():
                continue
            try:
                response = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"MCP server returned invalid JSON: {exc.msg}") from exc
            return response

        raise RuntimeError(f"MCP server timed out waiting for response to {payload.get('method')}")

    def notify(self, payload: dict[str, Any]) -> None:
        self._raise_if_exited(context="notification setup")
        if self.process.stdin is None:
            raise RuntimeError("MCP server stdin is not available")
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if self.process.stdin is not None:
            self.process.stdin.close()
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.process.stderr is not None:
            self.process.stderr.close()
        self._drain_stderr()


def _extract_mcp_text_result(response: dict[str, Any]) -> Any:
    if "error" in response:
        message = response["error"].get("message", "unknown MCP error")
        raise RuntimeError(f"MCP tool call failed: {message}")

    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("MCP response is missing a result object")

    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise RuntimeError("MCP response is missing content")

    first = content[0]
    if not isinstance(first, dict) or first.get("type") != "text":
        raise RuntimeError("MCP response content is not a text payload")

    text = first.get("text")
    if not isinstance(text, str):
        raise RuntimeError("MCP text payload is missing")

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"MCP text payload is not valid JSON: {exc.msg}") from exc


def _call_mcp_tool(session: _McpStdioSession, tool_name: str, arguments: dict[str, Any]) -> Any:
    response = session.request(
        {
            "jsonrpc": "2.0",
            "id": tool_name,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
    )
    return _extract_mcp_text_result(response)


def ensure_target_is_safe(target_palace: Path) -> None:
    if not target_palace.exists():
        return

    if not target_palace.is_dir():
        _raise_cli_error(
            stage="import",
            category="structural",
            summary="target path exists but is not a directory",
            details=[f"target path: {target_palace}"],
            where_to_look=[str(target_palace)],
            suggested_action="Choose a fresh target directory for the reconstructed palace and retry.",
        )

    existing = list(target_palace.iterdir())
    if existing:
        _raise_cli_error(
            stage="import",
            category="structural",
            summary="target directory is not empty and import would overwrite existing data",
            details=[
                f"target directory: {target_palace}",
                f"existing entries: {_preview_items(sorted(entry.name for entry in existing))}",
            ],
            where_to_look=[str(target_palace)],
            suggested_action="Use a new empty target directory or remove the existing target contents before retrying.",
        )


def import_drawers(export_dir: Path, target_palace: Path) -> dict[str, Any]:
    ensure_target_is_safe(target_palace)
    manifest, drawers = load_export_bundle(export_dir)
    export_analysis = _analyze_drawers(drawers)
    export_issues = _bundle_integrity_issues(manifest, export_analysis)
    if export_issues:
        _raise_cli_error(
            stage="import",
            category="data integrity",
            summary="export bundle failed integrity checks before import",
            details=export_issues,
            where_to_look=[
                str(export_dir),
                str(export_dir / DRAWERS_FILENAME),
                str(export_dir / EXPORT_MANIFEST_FILENAME),
            ],
            suggested_action="Inspect the bundle manifest and drawers file for the listed issues, then regenerate the bundle from a clean source palace.",
        )
    load_retrieval_query_plan_from_bundle(export_dir, manifest)
    load_usage_scenario_plan_from_bundle(export_dir, manifest, drawers)

    if manifest.get("source", {}).get("detected_format") != CLASS_CHROMA_0_6:
        _raise_cli_error(
            stage="import",
            category="structural",
            summary="export bundle does not declare a chroma_0_6 source palace",
            details=[f"declared source format: {manifest.get('source', {}).get('detected_format')}"],
            where_to_look=[str(export_dir / EXPORT_MANIFEST_FILENAME)],
            suggested_action="Regenerate the export bundle from a supported chroma_0_6 source palace before importing.",
        )

    target_palace.mkdir(parents=True, exist_ok=True)

    import chromadb

    try:
        client = chromadb.PersistentClient(path=str(target_palace))
        collection = client.create_collection(
            manifest["collection"]["name"], metadata=manifest["collection"]["metadata"]
        )
    except Exception as exc:
        _raise_cli_error(
            stage="import",
            category="structural",
            summary="target runtime could not create the reconstructed collection",
            details=[
                f"collection: {manifest['collection']['name']}",
                f"target palace: {target_palace}",
                f"runtime error: {exc}",
            ],
            where_to_look=[str(target_palace), str(export_dir / EXPORT_MANIFEST_FILENAME)],
            suggested_action="Check the target Python environment, chromadb installation, and collection metadata, then retry with a fresh target directory.",
        )

    batch_size = 500
    imported = 0
    for index in range(0, len(drawers), batch_size):
        batch = drawers[index : index + batch_size]
        batch_ids = [drawer["id"] for drawer in batch]
        try:
            collection.add(
                ids=batch_ids,
                documents=[drawer["document"] for drawer in batch],
                metadatas=[drawer["metadata"] for drawer in batch],
            )
        except Exception as exc:
            _raise_cli_error(
                stage="import",
                category="data integrity",
                summary="target runtime rejected a batch during import",
                details=[
                    f"batch index: {index // batch_size + 1}",
                    f"batch size: {len(batch)}",
                    f"affected drawer ids: {_preview_items(batch_ids)}",
                    f"runtime error: {exc}",
                ],
                where_to_look=[str(export_dir / DRAWERS_FILENAME), str(target_palace)],
                suggested_action="Inspect the listed drawer ids in the export bundle and verify their documents and metadata are acceptable to the target runtime.",
            )
        imported += len(batch)

    target_manifest = {
        "format_version": TARGET_FORMAT_VERSION,
        "created_at": _iso_timestamp_now(),
        "warnings": [
            "Experimental reconstruction target. This is not supported bridge infrastructure.",
            "Do not cut over automatically. Keep the source palace intact until manual review is complete.",
            "Validation is required before any manual switch, and passing validation does not imply supported MCP runtime behavior.",
        ],
        "target": {
            "palace_path": str(target_palace),
            "chromadb_version": _load_package_version("chromadb"),
            "mempalace_version": _load_package_version("mempalace"),
            "imported_drawer_count": imported,
        },
        "source_export": {
            "export_dir": str(export_dir),
            "created_at": manifest.get("created_at"),
            "source_palace_path": manifest.get("source", {}).get("palace_path"),
            "detected_format": manifest.get("source", {}).get("detected_format"),
            "drawer_count": export_analysis["drawer_count"],
        },
    }

    with (target_palace / TARGET_MANIFEST_FILENAME).open("w", encoding="utf-8") as handle:
        json.dump(target_manifest, handle, indent=2)
        handle.write("\n")

    return target_manifest


def record_retrieval_results(
    palace_path: Path,
    queries_path: Path,
    output_path: Path,
    *,
    label: str,
) -> dict[str, Any]:
    query_plan = load_retrieval_query_plan(queries_path)

    import chromadb

    try:
        client = chromadb.PersistentClient(path=str(palace_path))
        collection = client.get_collection(COLLECTION_NAME)
    except Exception as exc:
        _raise_cli_error(
            stage="retrieval recording",
            category="structural",
            summary="runtime could not open the MemPalace collection for retrieval checks",
            details=[
                f"palace path: {palace_path}",
                f"collection: {COLLECTION_NAME}",
                f"runtime error: {exc}",
            ],
            where_to_look=[str(palace_path), str(queries_path)],
            suggested_action="Verify the palace path, runtime environment, and collection name before rerunning retrieval recording.",
        )
    effective_top_k = min(query_plan["top_k"], collection.count())

    query_results: list[dict[str, Any]] = []
    for query in query_plan["queries"]:
        try:
            response = collection.query(
                query_texts=[query["query_text"]],
                n_results=effective_top_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            _raise_cli_error(
                stage="retrieval recording",
                category="retrieval mismatch",
                summary="runtime failed while executing a deterministic retrieval query",
                details=[
                    f"query id: {query['query_id']}",
                    f"anchor id: {query['anchor_id']}",
                    f"query text: {query['query_text']}",
                    f"runtime error: {exc}",
                ],
                where_to_look=[str(queries_path), str(palace_path)],
                suggested_action="Inspect the listed query in the retrieval plan and retry after confirming the target runtime can query the palace.",
            )

        ids = list(response.get("ids", [[]])[0])
        documents = list(response.get("documents", [[]])[0])
        metadatas = list(response.get("metadatas", [[]])[0])
        distances = list(response.get("distances", [[]])[0])

        query_results.append(
            {
                "query_id": query["query_id"],
                "query_text": query["query_text"],
                "anchor_id": query["anchor_id"],
                "result_count": len(ids),
                "ids": ids,
                "anchor_present": query["anchor_id"] in ids,
                "top_result_id": ids[0] if ids else None,
                "top_distance": distances[0] if distances else None,
                "results": [
                    {
                        "id": drawer_id,
                        "distance": distances[index] if index < len(distances) else None,
                        "document_preview": (
                            documents[index][:RETRIEVAL_QUERY_CHAR_LIMIT]
                            if index < len(documents) and isinstance(documents[index], str)
                            else None
                        ),
                        "metadata": metadatas[index] if index < len(metadatas) else None,
                    }
                    for index, drawer_id in enumerate(ids)
                ],
            }
        )

    result = {
        "format_version": RETRIEVAL_FORMAT_VERSION,
        "created_at": _iso_timestamp_now(),
        "label": label,
        "palace_path": str(palace_path),
        "queries_path": str(queries_path),
        "collection_name": COLLECTION_NAME,
        "chromadb_version": _load_package_version("chromadb"),
        "top_k": query_plan["top_k"],
        "effective_top_k": effective_top_k,
        "query_count": len(query_results),
        "results": query_results,
    }

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")

    return result


def record_usage_results(
    palace_path: Path,
    scenarios_path: Path,
    output_path: Path,
    *,
    label: str,
) -> dict[str, Any]:
    scenario_plan = load_usage_scenario_plan(scenarios_path)

    import chromadb

    try:
        client = chromadb.PersistentClient(path=str(palace_path))
        collection = client.get_collection(COLLECTION_NAME)
    except Exception as exc:
        _raise_cli_error(
            stage="usage recording",
            category="structural",
            summary="runtime could not open the MemPalace collection for usage checks",
            details=[
                f"palace path: {palace_path}",
                f"collection: {COLLECTION_NAME}",
                f"runtime error: {exc}",
            ],
            where_to_look=[str(palace_path), str(scenarios_path)],
            suggested_action="Verify the palace path, runtime environment, and collection name before rerunning usage recording.",
        )
    effective_top_k = min(scenario_plan["top_k"], collection.count())

    scenarios: list[dict[str, Any]] = []
    for scenario in scenario_plan["scenarios"]:
        steps: list[dict[str, Any]] = []
        for step in scenario["steps"]:
            try:
                response = collection.query(
                    query_texts=[step["query_text"]],
                    n_results=effective_top_k,
                    include=["documents", "metadatas", "distances"],
                )
            except Exception as exc:
                _raise_cli_error(
                    stage="usage recording",
                    category="retrieval mismatch",
                    summary="runtime failed while executing a deterministic usage step",
                    details=[
                        f"scenario id: {scenario['scenario_id']}",
                        f"step id: {step['step_id']}",
                        f"anchor id: {scenario['anchor_id']}",
                        f"query text: {step['query_text']}",
                        f"runtime error: {exc}",
                    ],
                    where_to_look=[str(scenarios_path), str(palace_path)],
                    suggested_action="Inspect the listed scenario step and confirm the selected runtime can query this palace.",
                )

            ids = list(response.get("ids", [[]])[0])
            documents = list(response.get("documents", [[]])[0])
            metadatas = list(response.get("metadatas", [[]])[0])
            distances = list(response.get("distances", [[]])[0])
            steps.append(
                {
                    "step_id": step["step_id"],
                    "query_text": step["query_text"],
                    "purpose": step["purpose"],
                    "result_count": len(ids),
                    "ids": ids,
                    "anchor_present": scenario["anchor_id"] in ids,
                    "top_result_id": ids[0] if ids else None,
                    "top_distance": distances[0] if distances else None,
                    "results": [
                        {
                            "id": drawer_id,
                            "distance": distances[index] if index < len(distances) else None,
                            "document_preview": (
                                documents[index][:RETRIEVAL_QUERY_CHAR_LIMIT]
                                if index < len(documents) and isinstance(documents[index], str)
                                else None
                            ),
                            "metadata": metadatas[index] if index < len(metadatas) else None,
                        }
                        for index, drawer_id in enumerate(ids)
                    ],
                }
            )

        final_step = steps[-1]
        scenarios.append(
            {
                "scenario_id": scenario["scenario_id"],
                "scenario_type": scenario["scenario_type"],
                "anchor_id": scenario["anchor_id"],
                "wing": scenario.get("wing"),
                "room": scenario.get("room"),
                "document_preview": scenario.get("document_preview"),
                "selection_reason": scenario.get("selection_reason"),
                "step_count": len(steps),
                "steps": steps,
                "final_step_id": final_step["step_id"],
                "final_anchor_present": final_step["anchor_present"],
                "final_result_count": final_step["result_count"],
            }
        )

    result = {
        "format_version": USAGE_FORMAT_VERSION,
        "created_at": _iso_timestamp_now(),
        "label": label,
        "palace_path": str(palace_path),
        "scenarios_path": str(scenarios_path),
        "collection_name": COLLECTION_NAME,
        "chromadb_version": _load_package_version("chromadb"),
        "top_k": scenario_plan["top_k"],
        "effective_top_k": effective_top_k,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")

    return result


def _index_retrieval_results(results_bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = results_bundle.get("results")
    if not isinstance(results, list) or not results:
        raise RuntimeError("Retrieval results bundle must contain a non-empty results list")

    indexed: dict[str, dict[str, Any]] = {}
    for result in results:
        if not isinstance(result, dict):
            raise RuntimeError("Retrieval result entries must be JSON objects")
        query_id = result.get("query_id")
        if not isinstance(query_id, str) or not query_id:
            raise RuntimeError("Retrieval result entry is missing query_id")
        indexed[query_id] = result
    return indexed


def load_retrieval_results(results_path: Path) -> dict[str, Any]:
    if not results_path.exists():
        raise RuntimeError(f"Retrieval results file is missing at {results_path}")

    try:
        results_bundle = json.loads(results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Retrieval results file is not valid JSON: {exc.msg}") from exc

    if not isinstance(results_bundle, dict):
        raise RuntimeError("Retrieval results file must be a JSON object")

    top_k = results_bundle.get("top_k")
    if not isinstance(top_k, int) or top_k <= 0:
        raise RuntimeError("Retrieval results file must declare a positive integer top_k")

    _index_retrieval_results(results_bundle)
    return results_bundle


def _index_usage_results(results_bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scenarios = results_bundle.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise RuntimeError("Usage results bundle must contain a non-empty scenarios list")

    indexed: dict[str, dict[str, Any]] = {}
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise RuntimeError("Usage result entries must be JSON objects")
        scenario_id = scenario.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise RuntimeError("Usage result entry is missing scenario_id")
        indexed[scenario_id] = scenario
    return indexed


def load_usage_results(results_path: Path) -> dict[str, Any]:
    if not results_path.exists():
        raise RuntimeError(f"Usage results file is missing at {results_path}")

    try:
        results_bundle = json.loads(results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Usage results file is not valid JSON: {exc.msg}") from exc

    if not isinstance(results_bundle, dict):
        raise RuntimeError("Usage results file must be a JSON object")

    top_k = results_bundle.get("top_k")
    if not isinstance(top_k, int) or top_k <= 0:
        raise RuntimeError("Usage results file must declare a positive integer top_k")

    _index_usage_results(results_bundle)
    return results_bundle


def compare_retrieval_results(
    source_results_path: Path,
    target_results_path: Path,
    *,
    count_tolerance: int = RETRIEVAL_COUNT_TOLERANCE,
    min_overlap_ratio: float = RETRIEVAL_MIN_OVERLAP_RATIO,
) -> dict[str, Any]:
    if count_tolerance < 0:
        raise RuntimeError("Retrieval count_tolerance must be non-negative")
    if not 0 <= min_overlap_ratio <= 1:
        raise RuntimeError("Retrieval min_overlap_ratio must be between 0 and 1")

    source_bundle = load_retrieval_results(source_results_path)
    target_bundle = load_retrieval_results(target_results_path)

    source_index = _index_retrieval_results(source_bundle)
    target_index = _index_retrieval_results(target_bundle)

    source_query_ids = sorted(source_index)
    target_query_ids = sorted(target_index)
    query_plan_matches = source_query_ids == target_query_ids and source_bundle["top_k"] == target_bundle["top_k"]

    compared_queries: list[dict[str, Any]] = []
    all_source_results_present = True
    all_source_anchor_present = True
    all_target_results_present = True
    all_target_anchor_present = True
    all_counts_within_tolerance = True
    all_overlap_meets_threshold = True

    for query_id in source_query_ids:
        if query_id not in target_index:
            continue

        source_result = source_index[query_id]
        target_result = target_index[query_id]
        source_ids = list(source_result.get("ids", []))
        target_ids = list(target_result.get("ids", []))
        overlap_ids = sorted(set(source_ids) & set(target_ids))
        source_count = len(source_ids)
        target_count = len(target_ids)
        overlap_count = len(overlap_ids)
        count_difference = abs(source_count - target_count)
        source_has_results = source_count > 0
        target_has_results = target_count > 0
        source_anchor_present = bool(source_result.get("anchor_present"))
        target_anchor_present = bool(target_result.get("anchor_present"))
        source_coverage = _ratio(overlap_count, source_count)
        target_coverage = _ratio(overlap_count, target_count)
        overlap_meets_threshold = source_coverage >= min_overlap_ratio
        counts_within_tolerance = count_difference <= count_tolerance

        mismatches: list[str] = []
        if not source_has_results:
            mismatches.append("source returned no results")
        if not source_anchor_present:
            mismatches.append("source did not retrieve anchor id")
        if source_has_results and not target_has_results:
            mismatches.append("target returned no results")
        if source_has_results and not target_anchor_present:
            mismatches.append("target did not retrieve anchor id")
        if not counts_within_tolerance:
            mismatches.append(f"result count difference {count_difference} exceeds tolerance {count_tolerance}")
        if source_has_results and not overlap_meets_threshold:
            mismatches.append(f"source overlap ratio {source_coverage} is below threshold {min_overlap_ratio}")

        compared_queries.append(
            {
                "query_id": query_id,
                "query_text": source_result.get("query_text"),
                "anchor_id": source_result.get("anchor_id"),
                "source_result_count": source_count,
                "target_result_count": target_count,
                "count_difference": count_difference,
                "source_ids": source_ids,
                "target_ids": target_ids,
                "overlap_ids": overlap_ids,
                "overlap_count": overlap_count,
                "source_coverage": source_coverage,
                "target_coverage": target_coverage,
                "source_top_result_id": source_result.get("top_result_id"),
                "target_top_result_id": target_result.get("top_result_id"),
                "checks": {
                    "source_has_results": source_has_results,
                    "source_anchor_present": source_anchor_present,
                    "target_has_results": target_has_results,
                    "target_anchor_present": target_anchor_present,
                    "result_count_within_tolerance": counts_within_tolerance,
                    "id_overlap_meets_threshold": overlap_meets_threshold,
                },
                "mismatches": mismatches,
            }
        )

        all_source_results_present &= source_has_results
        all_source_anchor_present &= source_anchor_present
        all_target_results_present &= (not source_has_results) or target_has_results
        all_target_anchor_present &= (not source_has_results) or target_anchor_present
        all_counts_within_tolerance &= counts_within_tolerance
        all_overlap_meets_threshold &= (not source_has_results) or overlap_meets_threshold

    checks = {
        "query_plan_matches": query_plan_matches,
        "source_results_present": all_source_results_present,
        "source_anchor_ids_present": all_source_anchor_present,
        "target_results_present": all_target_results_present,
        "target_anchor_ids_present": all_target_anchor_present,
        "result_counts_within_tolerance": all_counts_within_tolerance,
        "id_overlap_meets_threshold": all_overlap_meets_threshold,
    }

    mismatch_queries = [query["query_id"] for query in compared_queries if query["mismatches"]]
    return {
        "source_results_path": str(source_results_path),
        "target_results_path": str(target_results_path),
        "checks": checks,
        "tolerances": {
            "count_tolerance": count_tolerance,
            "min_overlap_ratio": min_overlap_ratio,
        },
        "summary": {
            "query_count": len(compared_queries),
            "mismatch_query_ids": mismatch_queries,
            "source_label": source_bundle.get("label"),
            "target_label": target_bundle.get("label"),
        },
        "queries": compared_queries,
        "valid": all(checks.values()) and len(compared_queries) == len(source_query_ids) == len(target_query_ids),
    }


def _index_usage_steps(steps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for step in steps:
        if not isinstance(step, dict):
            raise RuntimeError("Usage result steps must be JSON objects")
        step_id = step.get("step_id")
        if not isinstance(step_id, str) or not step_id:
            raise RuntimeError("Usage result step is missing step_id")
        indexed[step_id] = step
    return indexed


def compare_usage_results(
    source_results_path: Path,
    target_results_path: Path,
    *,
    count_tolerance: int = USAGE_COUNT_TOLERANCE,
    min_overlap_ratio: float = USAGE_MIN_OVERLAP_RATIO,
) -> dict[str, Any]:
    if count_tolerance < 0:
        raise RuntimeError("Usage count_tolerance must be non-negative")
    if not 0 <= min_overlap_ratio <= 1:
        raise RuntimeError("Usage min_overlap_ratio must be between 0 and 1")

    source_bundle = load_usage_results(source_results_path)
    target_bundle = load_usage_results(target_results_path)
    source_index = _index_usage_results(source_bundle)
    target_index = _index_usage_results(target_bundle)

    source_scenario_ids = sorted(source_index)
    target_scenario_ids = sorted(target_index)
    scenario_plan_matches = (
        source_scenario_ids == target_scenario_ids and source_bundle["top_k"] == target_bundle["top_k"]
    )

    compared_scenarios: list[dict[str, Any]] = []
    all_source_results_present = True
    all_source_anchor_present = True
    all_target_results_present = True
    all_target_anchor_present = True
    all_counts_within_tolerance = True
    all_overlap_meets_threshold = True
    recommendation = USAGE_ACCEPTABLE

    for scenario_id in source_scenario_ids:
        if scenario_id not in target_index:
            continue

        source_scenario = source_index[scenario_id]
        target_scenario = target_index[scenario_id]
        source_steps = _index_usage_steps(list(source_scenario.get("steps", [])))
        target_steps = _index_usage_steps(list(target_scenario.get("steps", [])))
        step_ids = sorted(source_steps)
        step_plan_matches = step_ids == sorted(target_steps)

        step_results: list[dict[str, Any]] = []
        scenario_has_unusable_mismatch = not step_plan_matches
        scenario_has_degraded_mismatch = False
        scenario_source_results_present = True
        scenario_source_anchor_present = True
        scenario_target_results_present = True
        scenario_target_anchor_present = True
        scenario_counts_within_tolerance = True
        scenario_overlap_meets_threshold = True

        for step_id in step_ids:
            if step_id not in target_steps:
                continue
            source_step = source_steps[step_id]
            target_step = target_steps[step_id]
            source_ids = list(source_step.get("ids", []))
            target_ids = list(target_step.get("ids", []))
            overlap_ids = sorted(set(source_ids) & set(target_ids))
            source_count = len(source_ids)
            target_count = len(target_ids)
            overlap_count = len(overlap_ids)
            source_has_results = source_count > 0
            target_has_results = target_count > 0
            source_anchor_present = bool(source_step.get("anchor_present"))
            target_anchor_present = bool(target_step.get("anchor_present"))
            source_overlap = _ratio(overlap_count, source_count)
            count_difference = abs(source_count - target_count)
            counts_within_tolerance = count_difference <= count_tolerance
            overlap_meets_threshold = source_overlap >= min_overlap_ratio

            mismatches: list[str] = []
            if not source_has_results:
                mismatches.append("source returned no results")
            if not source_anchor_present:
                mismatches.append("source did not retrieve anchor id")
            if source_has_results and not target_has_results:
                mismatches.append("target returned no results")
                scenario_has_unusable_mismatch = True
            if source_anchor_present and not target_anchor_present:
                mismatches.append("target did not retrieve anchor id")
                scenario_has_degraded_mismatch = True
            if not counts_within_tolerance:
                mismatches.append(f"result count difference {count_difference} exceeds tolerance {count_tolerance}")
                scenario_has_degraded_mismatch = True
            if source_has_results and not overlap_meets_threshold:
                mismatches.append(f"source overlap ratio {source_overlap} is below threshold {min_overlap_ratio}")
                if overlap_count == 0:
                    scenario_has_unusable_mismatch = True
                else:
                    scenario_has_degraded_mismatch = True

            step_results.append(
                {
                    "step_id": step_id,
                    "query_text": source_step.get("query_text"),
                    "source_result_count": source_count,
                    "target_result_count": target_count,
                    "count_difference": count_difference,
                    "source_ids": source_ids,
                    "target_ids": target_ids,
                    "overlap_ids": overlap_ids,
                    "overlap_count": overlap_count,
                    "source_overlap_ratio": source_overlap,
                    "source_top_result_id": source_step.get("top_result_id"),
                    "target_top_result_id": target_step.get("top_result_id"),
                    "checks": {
                        "source_has_results": source_has_results,
                        "source_anchor_present": source_anchor_present,
                        "target_has_results": target_has_results,
                        "target_anchor_present": target_anchor_present,
                        "result_count_within_tolerance": counts_within_tolerance,
                        "id_overlap_meets_threshold": overlap_meets_threshold,
                    },
                    "mismatches": mismatches,
                }
            )

            scenario_source_results_present &= source_has_results
            scenario_source_anchor_present &= source_anchor_present
            scenario_target_results_present &= (not source_has_results) or target_has_results
            scenario_target_anchor_present &= (not source_anchor_present) or target_anchor_present
            scenario_counts_within_tolerance &= counts_within_tolerance
            scenario_overlap_meets_threshold &= (not source_has_results) or overlap_meets_threshold

        scenario_recommendation = USAGE_ACCEPTABLE
        if scenario_has_unusable_mismatch:
            scenario_recommendation = USAGE_UNUSABLE
        elif scenario_has_degraded_mismatch:
            scenario_recommendation = USAGE_DEGRADED

        compared_scenarios.append(
            {
                "scenario_id": scenario_id,
                "scenario_type": source_scenario.get("scenario_type"),
                "anchor_id": source_scenario.get("anchor_id"),
                "step_plan_matches": step_plan_matches,
                "checks": {
                    "source_results_present": scenario_source_results_present,
                    "source_anchor_ids_present": scenario_source_anchor_present,
                    "target_results_present": scenario_target_results_present,
                    "target_anchor_ids_present": scenario_target_anchor_present,
                    "result_counts_within_tolerance": scenario_counts_within_tolerance,
                    "id_overlap_meets_threshold": scenario_overlap_meets_threshold,
                },
                "steps": step_results,
                "recommendation": scenario_recommendation,
            }
        )

        all_source_results_present &= scenario_source_results_present
        all_source_anchor_present &= scenario_source_anchor_present
        all_target_results_present &= scenario_target_results_present
        all_target_anchor_present &= scenario_target_anchor_present
        all_counts_within_tolerance &= scenario_counts_within_tolerance
        all_overlap_meets_threshold &= scenario_overlap_meets_threshold
        if scenario_recommendation == USAGE_UNUSABLE:
            recommendation = USAGE_UNUSABLE
        elif scenario_recommendation == USAGE_DEGRADED and recommendation != USAGE_UNUSABLE:
            recommendation = USAGE_DEGRADED

    checks = {
        "scenario_plan_matches": scenario_plan_matches,
        "source_results_present": all_source_results_present,
        "source_anchor_ids_present": all_source_anchor_present,
        "target_results_present": all_target_results_present,
        "target_anchor_ids_present": all_target_anchor_present,
        "result_counts_within_tolerance": all_counts_within_tolerance,
        "id_overlap_meets_threshold": all_overlap_meets_threshold,
    }
    if not scenario_plan_matches:
        recommendation = USAGE_UNUSABLE

    return {
        "source_results_path": str(source_results_path),
        "target_results_path": str(target_results_path),
        "checks": checks,
        "tolerances": {
            "count_tolerance": count_tolerance,
            "min_overlap_ratio": min_overlap_ratio,
        },
        "summary": {
            "scenario_count": len(compared_scenarios),
            "source_label": source_bundle.get("label"),
            "target_label": target_bundle.get("label"),
            "acceptable_scenarios": len(
                [scenario for scenario in compared_scenarios if scenario["recommendation"] == USAGE_ACCEPTABLE]
            ),
            "degraded_scenarios": len(
                [scenario for scenario in compared_scenarios if scenario["recommendation"] == USAGE_DEGRADED]
            ),
            "unusable_scenarios": len(
                [scenario for scenario in compared_scenarios if scenario["recommendation"] == USAGE_UNUSABLE]
            ),
        },
        "scenarios": compared_scenarios,
        "recommendation": recommendation,
        "valid": recommendation == USAGE_ACCEPTABLE
        and checks["scenario_plan_matches"]
        and checks["source_results_present"]
        and checks["target_results_present"]
        and checks["target_anchor_ids_present"]
        and checks["result_counts_within_tolerance"]
        and checks["id_overlap_meets_threshold"],
    }


def validate_mcp_runtime(
    export_dir: Path,
    palace_path: Path,
    *,
    python_executable: Path,
    launcher_script: Path,
    startup_grace_seconds: float = MCP_STARTUP_GRACE_SECONDS,
    request_timeout_seconds: float = MCP_REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    manifest, export_drawers = load_export_bundle(export_dir)
    query_plan = load_retrieval_query_plan_from_bundle(export_dir, manifest)
    if not query_plan["queries"]:
        raise RuntimeError("MCP runtime validation requires a non-empty retrieval query plan")

    export_analysis = _analyze_drawers(export_drawers)
    expected_count = export_analysis["drawer_count"]
    expected_taxonomy = export_analysis["wing_room_counts"]
    expected_documents = export_analysis["indexes"]["documents_by_id"]

    repo_root = Path(__file__).resolve().parents[1]
    resolved_python = Path(os.path.abspath(str(python_executable.expanduser())))
    resolved_launcher = launcher_script.expanduser()
    if not resolved_launcher.is_absolute():
        resolved_launcher = (repo_root / resolved_launcher).resolve()

    if not resolved_python.exists():
        raise RuntimeError(f"Python executable is missing at {resolved_python}")
    if not resolved_launcher.exists():
        raise RuntimeError(f"Launcher script is missing at {resolved_launcher}")

    uv_path = _resolve_uv_path()

    env = os.environ.copy()
    for variable in (
        "PYTHONHOME",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "UV_ACTIVE",
        "UV_PROJECT_ENVIRONMENT",
        "__PYVENV_LAUNCHER__",
        "PYTHONEXECUTABLE",
    ):
        env.pop(variable, None)
    env["MEMPALACE_PALACE_PATH"] = str(palace_path)
    if uv_path is not None:
        command = [
            uv_path,
            "run",
            "--python",
            str(resolved_python),
            "python",
            str(resolved_launcher),
        ]
    else:
        command = [str(resolved_python), str(resolved_launcher)]

    checks = {
        "server_started": False,
        "initialize_succeeded": False,
        "tools_listed": False,
        "required_tools_available": False,
        "status_matches_drawer_count": False,
        "status_reports_target_palace": False,
        "taxonomy_matches_export": False,
        "search_results_present": False,
        "anchor_texts_present": False,
        "server_stable_during_queries": False,
    }
    diagnostics: dict[str, Any] = {
        "command": command,
        "palace_path": str(palace_path),
        "tools_available": [],
        "status": None,
        "taxonomy": None,
        "queries": [],
        "stderr_preview": [],
    }

    session = _McpStdioSession(
        command=command,
        cwd=repo_root,
        env=env,
        startup_grace_seconds=startup_grace_seconds,
        request_timeout_seconds=request_timeout_seconds,
    )

    try:
        checks["server_started"] = session.process.poll() is None

        initialize_response = session.request(
            {
                "jsonrpc": "2.0",
                "id": "initialize",
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "clientInfo": {"name": "reconstruction-prototype", "version": "1"},
                },
            }
        )
        if "error" in initialize_response:
            raise RuntimeError(
                f"MCP initialize failed: {initialize_response['error'].get('message', 'unknown error')}"
            )
        checks["initialize_succeeded"] = True

        session.notify({"jsonrpc": "2.0", "method": "notifications/initialized"})

        tools_response = session.request({"jsonrpc": "2.0", "id": "tools-list", "method": "tools/list"})
        if "error" in tools_response:
            raise RuntimeError(f"MCP tools/list failed: {tools_response['error'].get('message', 'unknown error')}")
        tools = tools_response.get("result", {}).get("tools", [])
        if not isinstance(tools, list):
            raise RuntimeError("MCP tools/list returned an invalid tools payload")
        checks["tools_listed"] = True
        tool_names = sorted(
            [tool["name"] for tool in tools if isinstance(tool, dict) and isinstance(tool.get("name"), str)]
        )
        diagnostics["tools_available"] = tool_names
        required_tools = {"mempalace_status", "mempalace_get_taxonomy", "mempalace_search"}
        checks["required_tools_available"] = required_tools.issubset(set(tool_names))

        status_payload = _call_mcp_tool(session, "mempalace_status", {})
        diagnostics["status"] = status_payload
        if isinstance(status_payload, dict) and "error" not in status_payload:
            checks["status_matches_drawer_count"] = status_payload.get("total_drawers") == expected_count
            checks["status_reports_target_palace"] = (
                Path(str(status_payload.get("palace_path", ""))).resolve() == palace_path.resolve()
            )

        taxonomy_payload = _call_mcp_tool(session, "mempalace_get_taxonomy", {})
        diagnostics["taxonomy"] = taxonomy_payload
        if isinstance(taxonomy_payload, dict) and "error" not in taxonomy_payload:
            checks["taxonomy_matches_export"] = taxonomy_payload.get("taxonomy") == expected_taxonomy

        search_results_present = True
        anchor_texts_present = True
        for query in query_plan["queries"]:
            search_payload = _call_mcp_tool(
                session,
                "mempalace_search",
                {"query": query["query_text"], "limit": query_plan["top_k"]},
            )
            results = search_payload.get("results", []) if isinstance(search_payload, dict) else []
            anchor_text = expected_documents[query["anchor_id"]]
            result_texts = [result.get("text") for result in results if isinstance(result, dict)]
            anchor_present = anchor_text in result_texts
            result_count = len(results)

            mismatches: list[str] = []
            if isinstance(search_payload, dict) and "error" in search_payload:
                mismatches.append(str(search_payload["error"]))
            if result_count == 0:
                mismatches.append("search returned no results")
                search_results_present = False
            if not anchor_present:
                mismatches.append("anchor text not present in MCP search results")
                anchor_texts_present = False

            diagnostics["queries"].append(
                {
                    "query_id": query["query_id"],
                    "query_text": query["query_text"],
                    "anchor_id": query["anchor_id"],
                    "anchor_text_present": anchor_present,
                    "result_count": result_count,
                    "top_result_preview": result_texts[0][:RETRIEVAL_QUERY_CHAR_LIMIT] if result_texts else None,
                    "mismatches": mismatches,
                }
            )

        checks["search_results_present"] = search_results_present
        checks["anchor_texts_present"] = anchor_texts_present
        checks["server_stable_during_queries"] = session.process.poll() is None
    finally:
        diagnostics["stderr_preview"] = session.stderr_preview()
        session.close()

    return {
        "export_dir": str(export_dir),
        "palace_path": str(palace_path),
        "python_executable": str(resolved_python),
        "launcher_script": str(resolved_launcher),
        "checks": checks,
        "diagnostics": diagnostics,
        "valid": all(checks.values()),
    }


def validate_reconstruction(export_dir: Path, target_palace: Path) -> dict[str, Any]:
    manifest, export_drawers = load_export_bundle(export_dir)
    load_retrieval_query_plan_from_bundle(export_dir, manifest)
    load_usage_scenario_plan_from_bundle(export_dir, manifest, export_drawers)
    export_analysis = _analyze_drawers(export_drawers)
    expected_count = export_analysis["drawer_count"]
    expected_counts = export_analysis["wing_room_counts"]
    sample_ids = manifest.get("summary", {}).get("sample_ids", export_analysis["sample_ids"])
    export_bundle_issues = _bundle_integrity_issues(manifest, export_analysis)

    import chromadb

    client = chromadb.PersistentClient(path=str(target_palace))
    collection = client.get_collection(COLLECTION_NAME)

    actual_count = collection.count()
    try:
        target_drawers, embedding_diagnostics = _fetch_collection_drawers(collection, include_embeddings=True)
    except Exception as exc:
        target_drawers, embedding_diagnostics = _fetch_collection_drawers(collection, include_embeddings=False)
        embedding_diagnostics = {
            "checked": False,
            "accessible": False,
            "reason": str(exc),
            "checked_count": 0,
            "present_count": 0,
            "missing_ids": [],
        }

    target_analysis = _analyze_drawers(target_drawers)
    actual_counts = target_analysis["wing_room_counts"]
    sample_lookup = collection.get(ids=sample_ids, include=["metadatas"])
    found_sample_ids = sample_lookup.get("ids", [])

    export_ids = set(export_analysis["ids"])
    target_ids = set(target_analysis["ids"])
    missing_ids = sorted(export_ids - target_ids)
    unexpected_ids = sorted(target_ids - export_ids)
    shared_ids = sorted(export_ids & target_ids)

    content_mismatch_ids = sorted(
        [
            drawer_id
            for drawer_id in shared_ids
            if export_analysis["indexes"]["document_hashes"][drawer_id]
            != target_analysis["indexes"]["document_hashes"][drawer_id]
        ]
    )

    metadata_mismatch_ids = sorted(
        [
            drawer_id
            for drawer_id in shared_ids
            if export_analysis["indexes"]["metadata_hashes"].get(drawer_id)
            != target_analysis["indexes"]["metadata_hashes"].get(drawer_id)
        ]
    )

    missing_metadata_keys = {
        drawer_id: sorted(
            set(export_analysis["indexes"]["metadata_by_id"][drawer_id])
            - set(target_analysis["indexes"]["metadata_by_id"].get(drawer_id, {}))
        )
        for drawer_id in shared_ids
        if set(export_analysis["indexes"]["metadata_by_id"][drawer_id])
        - set(target_analysis["indexes"]["metadata_by_id"].get(drawer_id, {}))
    }

    checks = {
        "drawer_count_matches": actual_count == expected_count,
        "fetched_drawer_count_matches_collection": len(target_drawers) == actual_count,
        "wing_room_counts_match": actual_counts == expected_counts,
        "sample_ids_present": sorted(found_sample_ids) == sorted(sample_ids),
        "target_manifest_present": (target_palace / TARGET_MANIFEST_FILENAME).exists(),
        "export_bundle_integrity_ok": not export_bundle_issues,
        "export_ids_unique": not export_analysis["id_integrity"]["duplicate_ids"]
        and not export_analysis["id_integrity"]["blank_id_records"],
        "target_ids_unique": not target_analysis["id_integrity"]["duplicate_ids"]
        and not target_analysis["id_integrity"]["blank_id_records"],
        "id_sets_match": not missing_ids and not unexpected_ids,
        "documents_non_empty": not export_analysis["content_integrity"]["non_string_document_ids"]
        and not export_analysis["content_integrity"]["empty_document_ids"]
        and not target_analysis["content_integrity"]["non_string_document_ids"]
        and not target_analysis["content_integrity"]["empty_document_ids"],
        "content_length_profile_matches": export_analysis["content_integrity"]["length_profile"]
        == target_analysis["content_integrity"]["length_profile"],
        "content_hashes_match": not content_mismatch_ids,
        "metadata_structures_valid": not export_analysis["metadata_integrity"]["structural_issue_ids"]
        and not target_analysis["metadata_integrity"]["structural_issue_ids"],
        "metadata_keys_preserved": not missing_metadata_keys,
        "metadata_values_match": not metadata_mismatch_ids,
    }

    if embedding_diagnostics["checked"]:
        checks["embeddings_present"] = not embedding_diagnostics["missing_ids"]

    return {
        "export_dir": str(export_dir),
        "target_palace": str(target_palace),
        "checks": checks,
        "expected_drawer_count": expected_count,
        "actual_drawer_count": actual_count,
        "fetched_drawer_count": len(target_drawers),
        "expected_wing_room_counts": expected_counts,
        "actual_wing_room_counts": actual_counts,
        "sample_ids_checked": sample_ids,
        "sample_ids_found": found_sample_ids,
        "diagnostics": {
            "export_bundle_issues": export_bundle_issues,
            "ids": {
                "missing_in_target": missing_ids,
                "unexpected_in_target": unexpected_ids,
                "duplicate_in_export": export_analysis["id_integrity"]["duplicate_ids"],
                "duplicate_in_target": target_analysis["id_integrity"]["duplicate_ids"],
                "blank_in_export": export_analysis["id_integrity"]["blank_id_records"],
                "blank_in_target": target_analysis["id_integrity"]["blank_id_records"],
            },
            "content": {
                "empty_in_export": export_analysis["content_integrity"]["empty_document_ids"],
                "empty_in_target": target_analysis["content_integrity"]["empty_document_ids"],
                "non_string_in_export": export_analysis["content_integrity"]["non_string_document_ids"],
                "non_string_in_target": target_analysis["content_integrity"]["non_string_document_ids"],
                "mismatched_ids": content_mismatch_ids,
                "expected_length_profile": export_analysis["content_integrity"]["length_profile"],
                "actual_length_profile": target_analysis["content_integrity"]["length_profile"],
            },
            "metadata": {
                "structural_issue_ids_in_export": export_analysis["metadata_integrity"]["structural_issue_ids"],
                "structural_issue_ids_in_target": target_analysis["metadata_integrity"]["structural_issue_ids"],
                "mismatched_ids": metadata_mismatch_ids,
                "missing_keys_in_target": missing_metadata_keys,
            },
            "embeddings": embedding_diagnostics,
        },
        "valid": all(checks.values()),
    }


def _build_validation_error_groups(result: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics = result["diagnostics"]
    groups: list[dict[str, Any]] = []

    structural_items: list[str] = []
    if not result["checks"]["drawer_count_matches"]:
        structural_items.append(
            f"drawer count mismatch: expected {result['expected_drawer_count']} but target reports {result['actual_drawer_count']}"
        )
    if not result["checks"]["fetched_drawer_count_matches_collection"]:
        structural_items.append(
            f"collection count mismatch: collection.count()={result['actual_drawer_count']} but fetched {result['fetched_drawer_count']} drawers during validation"
        )
    if not result["checks"]["wing_room_counts_match"]:
        structural_items.append("wing/room counts differ between export bundle and target collection")
    if not result["checks"]["sample_ids_present"]:
        missing_samples = sorted(set(result["sample_ids_checked"]) - set(result["sample_ids_found"]))
        structural_items.append(f"sample drawer ids missing from target: {_preview_items(missing_samples)}")
    if not result["checks"]["target_manifest_present"]:
        structural_items.append("target reconstruction manifest is missing")
    if not result["checks"]["export_bundle_integrity_ok"]:
        structural_items.extend(diagnostics["export_bundle_issues"])
    if structural_items:
        groups.append(
            {
                "category": "structural",
                "items": structural_items,
                "where_to_look": [
                    result["export_dir"],
                    result["target_palace"],
                    f"{result['target_palace']}/{TARGET_MANIFEST_FILENAME}",
                ],
                "suggested_action": "Start by checking the bundle manifest, target manifest, and wing/room counts before inspecting individual drawers.",
            }
        )

    data_integrity_items: list[str] = []
    ids = diagnostics["ids"]
    content = diagnostics["content"]
    metadata = diagnostics["metadata"]
    embeddings = diagnostics["embeddings"]
    if ids["missing_in_target"]:
        data_integrity_items.append(f"missing drawers in target: {_preview_items(ids['missing_in_target'])}")
    if ids["unexpected_in_target"]:
        data_integrity_items.append(f"unexpected drawers in target: {_preview_items(ids['unexpected_in_target'])}")
    if ids["duplicate_in_export"]:
        data_integrity_items.append(f"duplicate drawer ids in export: {_preview_items(ids['duplicate_in_export'])}")
    if ids["duplicate_in_target"]:
        data_integrity_items.append(f"duplicate drawer ids in target: {_preview_items(ids['duplicate_in_target'])}")
    if content["mismatched_ids"]:
        data_integrity_items.append(f"content hash mismatches: {_preview_items(content['mismatched_ids'])}")
    if metadata["mismatched_ids"]:
        data_integrity_items.append(f"metadata mismatches: {_preview_items(metadata['mismatched_ids'])}")
    if metadata["missing_keys_in_target"]:
        drawer_id = sorted(metadata["missing_keys_in_target"])[0]
        data_integrity_items.append(
            f"metadata keys missing in target for {drawer_id}: {_preview_items(metadata['missing_keys_in_target'][drawer_id])}"
        )
    if embeddings.get("missing_ids"):
        data_integrity_items.append(f"drawers missing embeddings: {_preview_items(embeddings['missing_ids'])}")
    if data_integrity_items:
        groups.append(
            {
                "category": "data integrity",
                "items": data_integrity_items,
                "where_to_look": [
                    f"{result['export_dir']}/{DRAWERS_FILENAME}",
                    result["target_palace"],
                ],
                "suggested_action": "Inspect the listed drawer ids in the export bundle and compare them with the target collection contents.",
            }
        )

    return groups


def _build_retrieval_error_groups(result: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    structural_items: list[str] = []
    if not result["checks"]["query_plan_matches"]:
        structural_items.append("source and target retrieval result bundles do not share the same query plan or top_k")
    if structural_items:
        groups.append(
            {
                "category": "structural",
                "items": structural_items,
                "where_to_look": [result["source_results_path"], result["target_results_path"]],
                "suggested_action": "Re-record source and target retrieval results from the same export bundle before comparing them again.",
            }
        )

    mismatch_items: list[str] = []
    for query in result["queries"]:
        if not query["mismatches"]:
            continue
        mismatch_items.append(
            f"{query['query_id']} anchor={query['anchor_id']} source={query['source_result_count']} "
            f"target={query['target_result_count']} overlap={query['overlap_count']} "
            f"issues={_preview_items(query['mismatches'])}"
        )
    if mismatch_items:
        groups.append(
            {
                "category": "retrieval mismatch",
                "items": mismatch_items,
                "where_to_look": [result["source_results_path"], result["target_results_path"]],
                "suggested_action": "Review the listed query ids and anchor drawers in the retrieval result artifacts to see whether the target missed the expected semantic neighborhood.",
            }
        )

    return groups


def _build_usage_error_groups(result: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    if not result["checks"]["scenario_plan_matches"]:
        groups.append(
            {
                "category": "structural",
                "items": ["source and target usage result bundles do not share the same scenario plan or top_k"],
                "where_to_look": [result["source_results_path"], result["target_results_path"]],
                "suggested_action": "Re-record usage results from the same export bundle before comparing them again.",
            }
        )

    mismatch_items: list[str] = []
    for scenario in result["scenarios"]:
        if scenario["recommendation"] == USAGE_ACCEPTABLE:
            continue
        step_summaries = [
            f"{step['step_id']} issues={_preview_items(step['mismatches'])}"
            for step in scenario["steps"]
            if step["mismatches"]
        ]
        mismatch_items.append(
            f"{scenario['scenario_id']} type={scenario['scenario_type']} recommendation={scenario['recommendation']} "
            f"steps={_preview_items(step_summaries)}"
        )
    if mismatch_items:
        groups.append(
            {
                "category": "retrieval mismatch",
                "items": mismatch_items,
                "where_to_look": [result["source_results_path"], result["target_results_path"]],
                "suggested_action": "Inspect the listed scenarios step by step to see where target retrieval diverged from the source behavior.",
            }
        )
    return groups


def _build_mcp_runtime_error_groups(result: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics = result["diagnostics"]
    groups: list[dict[str, Any]] = []
    structural_items: list[str] = []
    if not result["checks"]["server_started"]:
        structural_items.append("server did not stay alive long enough to serve MCP requests")
    if not result["checks"]["initialize_succeeded"]:
        structural_items.append("MCP initialize did not succeed")
    if not result["checks"]["required_tools_available"]:
        structural_items.append(
            f"required tools missing: expected mempalace_status, mempalace_get_taxonomy, mempalace_search but got {_preview_items(diagnostics['tools_available'])}"
        )
    if not result["checks"]["status_matches_drawer_count"]:
        structural_items.append("mempalace_status drawer count does not match the export bundle")
    if not result["checks"]["taxonomy_matches_export"]:
        structural_items.append("MCP taxonomy does not match export wing/room counts")
    if structural_items:
        groups.append(
            {
                "category": "structural",
                "items": structural_items,
                "where_to_look": [result["palace_path"], result["launcher_script"]],
                "suggested_action": "Check MCP startup, the selected launcher, and the target palace path before trusting runtime behavior.",
            }
        )

    mismatch_items = [
        f"{query['query_id']} anchor={query['anchor_id']} results={query['result_count']} issues={_preview_items(query['mismatches'])}"
        for query in diagnostics["queries"]
        if query["mismatches"]
    ]
    if mismatch_items or diagnostics["stderr_preview"]:
        items = mismatch_items.copy()
        if diagnostics["stderr_preview"]:
            items.append(f"server stderr preview: {_preview_items(diagnostics['stderr_preview'])}")
        groups.append(
            {
                "category": "retrieval mismatch",
                "items": items,
                "where_to_look": [result["palace_path"]],
                "suggested_action": "Inspect the MCP search responses for the listed queries and compare them with the export bundle anchors.",
            }
        )
    return groups


def _print_export_result(manifest: dict[str, Any], export_dir: Path) -> None:
    print(f"[OK]    Exported {manifest['summary']['drawer_count']} drawers to {export_dir}")
    print(
        f"[INFO]  Source detection: {manifest['source']['detected_format']} "
        f"({manifest['source']['detection_confidence']})"
    )
    retrieval = manifest.get("retrieval_validation", {})
    if retrieval:
        print(f"[INFO]  Retrieval queries: {retrieval.get('query_count')} " f"(top_k={retrieval.get('top_k')})")
    usage = manifest.get("usage_validation", {})
    if usage:
        print(f"[INFO]  Usage scenarios: {usage.get('scenario_count')} " f"(top_k={usage.get('top_k')})")
    if manifest["warnings"]:
        for warning in manifest["warnings"]:
            print(f"[WARN]  {warning}")


def _print_import_result(target_manifest: dict[str, Any], target_palace: Path) -> None:
    print(f"[OK]    Imported {target_manifest['target']['imported_drawer_count']} drawers into {target_palace}")
    for warning in target_manifest["warnings"]:
        print(f"[WARN]  {warning}")


def _print_retrieval_record_result(result: dict[str, Any], output_path: Path) -> None:
    print(f"[OK]    Recorded retrieval results for {result['query_count']} queries to {output_path}")
    print(f"[INFO]  Label: {result['label']}")
    print(f"[INFO]  Palace: {result['palace_path']}")


def _print_usage_record_result(result: dict[str, Any], output_path: Path) -> None:
    print(f"[OK]    Recorded usage results for {result['scenario_count']} scenarios to {output_path}")
    print(f"[INFO]  Label: {result['label']}")
    print(f"[INFO]  Palace: {result['palace_path']}")


def _print_validation_result(result: dict[str, Any]) -> None:
    if result["valid"]:
        print("[OK]    Reconstruction validation passed")
    else:
        print("[ERROR] Reconstruction validation failed", file=sys.stderr)

    for check_name, passed in result["checks"].items():
        prefix = "[OK]   " if passed else "[FAIL] "
        stream = sys.stdout if passed else sys.stderr
        print(f"{prefix} {check_name}", file=stream)

    diagnostics = result["diagnostics"]
    print(f"[INFO]  Drawer counts: expected={result['expected_drawer_count']} actual={result['actual_drawer_count']}")
    print(
        "[INFO]  Content chars: "
        f"expected_total={diagnostics['content']['expected_length_profile']['total_chars']} "
        f"actual_total={diagnostics['content']['actual_length_profile']['total_chars']}"
    )

    if diagnostics["ids"]["missing_in_target"]:
        print(
            f"[INFO]  Missing ids: {_preview_items(diagnostics['ids']['missing_in_target'])}",
            file=sys.stderr,
        )
    if diagnostics["ids"]["unexpected_in_target"]:
        print(
            f"[INFO]  Unexpected ids: {_preview_items(diagnostics['ids']['unexpected_in_target'])}",
            file=sys.stderr,
        )
    if diagnostics["content"]["mismatched_ids"]:
        print(
            f"[INFO]  Content mismatches: {_preview_items(diagnostics['content']['mismatched_ids'])}",
            file=sys.stderr,
        )
    if diagnostics["metadata"]["mismatched_ids"]:
        print(
            f"[INFO]  Metadata mismatches: {_preview_items(diagnostics['metadata']['mismatched_ids'])}",
            file=sys.stderr,
        )
    if diagnostics["metadata"]["missing_keys_in_target"]:
        print(
            "[INFO]  Metadata keys missing in target: "
            f"{_preview_items(sorted(diagnostics['metadata']['missing_keys_in_target']))}",
            file=sys.stderr,
        )

    embeddings = diagnostics["embeddings"]
    if embeddings["checked"]:
        print(f"[INFO]  Embeddings present: {embeddings['present_count']}/{embeddings['checked_count']}")
    elif not embeddings["accessible"]:
        print(f"[INFO]  Embedding check skipped: {embeddings['reason']}")

    if not result["valid"]:
        error_groups = _build_validation_error_groups(result)
        debug_artifact_path = _write_debug_artifact(
            Path(result["export_dir"]) / VALIDATION_DEBUG_FILENAME,
            {"error_groups": error_groups, "result": result},
        )
        _print_error_groups("Validation failure summary", error_groups, debug_artifact_path=debug_artifact_path)


def _print_retrieval_comparison_result(result: dict[str, Any]) -> None:
    if result["valid"]:
        print("[OK]    Retrieval validation passed")
    else:
        print("[ERROR] Retrieval validation failed", file=sys.stderr)

    for check_name, passed in result["checks"].items():
        prefix = "[OK]   " if passed else "[FAIL] "
        stream = sys.stdout if passed else sys.stderr
        print(f"{prefix} {check_name}", file=stream)

    print(
        "[INFO]  Query comparison: "
        f"{result['summary']['query_count']} queries, "
        f"count_tolerance={result['tolerances']['count_tolerance']}, "
        f"min_overlap_ratio={result['tolerances']['min_overlap_ratio']}"
    )

    for query in result["queries"]:
        if not query["mismatches"]:
            continue
        print(
            f"[INFO]  {query['query_id']} overlap={query['overlap_count']} "
            f"source_count={query['source_result_count']} target_count={query['target_result_count']}",
            file=sys.stderr,
        )
        if query["mismatches"]:
            print(
                f"[INFO]  {query['query_id']} mismatches: {_preview_items(query['mismatches'])}",
                file=sys.stderr,
            )
        if query["overlap_ids"]:
            print(
                f"[INFO]  {query['query_id']} overlap ids: {_preview_items(query['overlap_ids'])}",
                file=sys.stderr,
            )

    if not result["valid"]:
        error_groups = _build_retrieval_error_groups(result)
        debug_artifact_path = _write_debug_artifact(
            Path(result["target_results_path"]).resolve().parent / RETRIEVAL_DEBUG_FILENAME,
            {"error_groups": error_groups, "result": result},
        )
        _print_error_groups("Retrieval failure summary", error_groups, debug_artifact_path=debug_artifact_path)


def _print_mcp_runtime_result(result: dict[str, Any]) -> None:
    if result["valid"]:
        print("[OK]    MCP runtime validation passed")
    else:
        print("[ERROR] MCP runtime validation failed", file=sys.stderr)

    for check_name, passed in result["checks"].items():
        prefix = "[OK]   " if passed else "[FAIL] "
        stream = sys.stdout if passed else sys.stderr
        print(f"{prefix} {check_name}", file=stream)

    print(f"[INFO]  Launcher: {result['python_executable']} {result['launcher_script']}")
    print(f"[INFO]  Palace: {result['palace_path']}")

    diagnostics = result["diagnostics"]
    for query in diagnostics["queries"]:
        if not query["mismatches"]:
            continue
        print(
            f"[INFO]  {query['query_id']} result_count={query['result_count']} "
            f"anchor_text_present={query['anchor_text_present']}",
            file=sys.stderr,
        )
        print(
            f"[INFO]  {query['query_id']} mismatches: {_preview_items(query['mismatches'])}",
            file=sys.stderr,
        )

    if diagnostics["stderr_preview"]:
        print(
            f"[INFO]  Server stderr: {_preview_items(diagnostics['stderr_preview'])}",
            file=sys.stderr,
        )

    if not result["valid"]:
        error_groups = _build_mcp_runtime_error_groups(result)
        debug_artifact_path = _write_debug_artifact(
            Path(result["export_dir"]) / MCP_RUNTIME_DEBUG_FILENAME,
            {"error_groups": error_groups, "result": result},
        )
        _print_error_groups("MCP runtime failure summary", error_groups, debug_artifact_path=debug_artifact_path)


def _print_usage_comparison_result(result: dict[str, Any]) -> None:
    if result["valid"]:
        print("[OK]    Usage comparison passed")
    else:
        print("[ERROR] Usage comparison detected divergence", file=sys.stderr)

    for check_name, passed in result["checks"].items():
        warning = not passed and result["recommendation"] == USAGE_ACCEPTABLE and check_name.startswith("source_")
        if warning:
            prefix = "[WARN] "
            stream = sys.stdout
        else:
            prefix = "[OK]   " if passed else "[FAIL] "
            stream = sys.stdout if passed else sys.stderr
        print(f"{prefix} {check_name}", file=stream)

    summary = result["summary"]
    print(
        "[INFO]  Usage recommendation: "
        f"{result['recommendation']} "
        f"(acceptable={summary['acceptable_scenarios']} "
        f"degraded={summary['degraded_scenarios']} "
        f"unusable={summary['unusable_scenarios']})"
    )

    for scenario in result["scenarios"]:
        if scenario["recommendation"] == USAGE_ACCEPTABLE:
            continue
        print(
            f"[INFO]  {scenario['scenario_id']} type={scenario['scenario_type']} "
            f"recommendation={scenario['recommendation']}",
            file=sys.stderr,
        )
        for step in scenario["steps"]:
            if not step["mismatches"]:
                continue
            print(
                f"[INFO]  {scenario['scenario_id']} {step['step_id']} mismatches: "
                f"{_preview_items(step['mismatches'])}",
                file=sys.stderr,
            )
            if step["overlap_ids"]:
                print(
                    f"[INFO]  {scenario['scenario_id']} {step['step_id']} overlap ids: "
                    f"{_preview_items(step['overlap_ids'])}",
                    file=sys.stderr,
                )

    if not result["valid"]:
        error_groups = _build_usage_error_groups(result)
        debug_artifact_path = _write_debug_artifact(
            Path(result["target_results_path"]).resolve().parent / USAGE_DEBUG_FILENAME,
            {"error_groups": error_groups, "result": result},
        )
        _print_error_groups("Usage failure summary", error_groups, debug_artifact_path=debug_artifact_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Non-destructive reconstruction tool for exporting a "
            "chroma_0_6 palace and rebuilding it into a separate target."
        )
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show full tracebacks on failure instead of concise error messages",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export logical drawers from a source palace")
    export_parser.add_argument("--source-palace", required=True, help="Path to the source palace")
    export_parser.add_argument("--output-dir", required=True, help="Path to a new export bundle directory")
    export_parser.add_argument("--json", action="store_true", help="Print JSON result")

    import_parser = subparsers.add_parser("import", help="Import an export bundle into a fresh target palace")
    import_parser.add_argument("--export-dir", required=True, help="Path to an export bundle directory")
    import_parser.add_argument("--target-palace", required=True, help="Path to a new target palace directory")
    import_parser.add_argument("--json", action="store_true", help="Print JSON result")

    validate_parser = subparsers.add_parser(
        "validate", help="Validate a rebuilt target palace against an export bundle"
    )
    validate_parser.add_argument("--export-dir", required=True, help="Path to an export bundle directory")
    validate_parser.add_argument("--target-palace", required=True, help="Path to the rebuilt target palace")
    validate_parser.add_argument("--json", action="store_true", help="Print JSON result")

    record_retrieval_parser = subparsers.add_parser(
        "record-retrieval",
        help="Run deterministic retrieval queries against one palace and store the results",
    )
    record_retrieval_parser.add_argument("--palace", required=True, help="Path to the palace to query")
    record_retrieval_parser.add_argument(
        "--queries-file",
        required=True,
        help="Path to the retrieval queries JSON file generated from the export bundle",
    )
    record_retrieval_parser.add_argument(
        "--output",
        required=True,
        help="Path to write the retrieval results JSON artifact",
    )
    record_retrieval_parser.add_argument(
        "--label", required=True, help="Label for this result set, e.g. source or target"
    )
    record_retrieval_parser.add_argument("--json", action="store_true", help="Print JSON result")

    compare_retrieval_parser = subparsers.add_parser(
        "compare-retrieval",
        help="Compare recorded retrieval results from source and reconstructed target palaces",
    )
    compare_retrieval_parser.add_argument(
        "--source-results",
        required=True,
        help="Path to the source retrieval results JSON artifact",
    )
    compare_retrieval_parser.add_argument(
        "--target-results",
        required=True,
        help="Path to the target retrieval results JSON artifact",
    )
    compare_retrieval_parser.add_argument(
        "--count-tolerance",
        type=int,
        default=RETRIEVAL_COUNT_TOLERANCE,
        help="Maximum allowed absolute difference in result counts per query",
    )
    compare_retrieval_parser.add_argument(
        "--min-overlap-ratio",
        type=float,
        default=RETRIEVAL_MIN_OVERLAP_RATIO,
        help="Minimum required overlap ratio against the source result set",
    )
    compare_retrieval_parser.add_argument("--json", action="store_true", help="Print JSON result")

    record_usage_parser = subparsers.add_parser(
        "record-usage",
        help="Run deterministic usage scenarios against one palace and store the results",
    )
    record_usage_parser.add_argument("--palace", required=True, help="Path to the palace to query")
    record_usage_parser.add_argument(
        "--scenarios-file",
        required=True,
        help="Path to the usage scenarios JSON file generated from the export bundle",
    )
    record_usage_parser.add_argument(
        "--output",
        required=True,
        help="Path to write the usage results JSON artifact",
    )
    record_usage_parser.add_argument("--label", required=True, help="Label for this result set, e.g. source or target")
    record_usage_parser.add_argument("--json", action="store_true", help="Print JSON result")

    compare_usage_parser = subparsers.add_parser(
        "compare-usage",
        help="Compare recorded usage results from source and reconstructed target palaces",
    )
    compare_usage_parser.add_argument(
        "--source-results",
        required=True,
        help="Path to the source usage results JSON artifact",
    )
    compare_usage_parser.add_argument(
        "--target-results",
        required=True,
        help="Path to the target usage results JSON artifact",
    )
    compare_usage_parser.add_argument(
        "--count-tolerance",
        type=int,
        default=USAGE_COUNT_TOLERANCE,
        help="Maximum allowed absolute difference in result counts per step",
    )
    compare_usage_parser.add_argument(
        "--min-overlap-ratio",
        type=float,
        default=USAGE_MIN_OVERLAP_RATIO,
        help="Minimum required overlap ratio against the source result set",
    )
    compare_usage_parser.add_argument("--json", action="store_true", help="Print JSON result")

    validate_mcp_parser = subparsers.add_parser(
        "validate-mcp-runtime",
        help="Probe MCP startup and tool queries against a palace using an experimental launcher",
    )
    validate_mcp_parser.add_argument("--export-dir", required=True, help="Path to an export bundle directory")
    validate_mcp_parser.add_argument("--palace", required=True, help="Path to the palace to validate through MCP")
    validate_mcp_parser.add_argument(
        "--python",
        required=True,
        help="Path to the Python executable in the runtime environment that should launch the MCP server",
    )
    validate_mcp_parser.add_argument(
        "--launcher-script",
        default="scripts/run_mcp_server_exploration.py",
        help="Launcher script to execute with the selected Python (default: exploration launcher)",
    )
    validate_mcp_parser.add_argument("--json", action="store_true", help="Print JSON result")

    args = parser.parse_args()

    try:
        if args.command == "export":
            result = export_drawers(
                source_palace=Path(args.source_palace).expanduser().resolve(),
                export_dir=Path(args.output_dir).expanduser().resolve(),
            )
            if args.json:
                json.dump(result, sys.stdout, indent=2)
                print()
            else:
                _print_export_result(result, Path(args.output_dir).expanduser().resolve())
            return 0

        if args.command == "import":
            result = import_drawers(
                export_dir=Path(args.export_dir).expanduser().resolve(),
                target_palace=Path(args.target_palace).expanduser().resolve(),
            )
            if args.json:
                json.dump(result, sys.stdout, indent=2)
                print()
            else:
                _print_import_result(result, Path(args.target_palace).expanduser().resolve())
            return 0

        if args.command == "record-retrieval":
            result = record_retrieval_results(
                palace_path=Path(args.palace).expanduser().resolve(),
                queries_path=Path(args.queries_file).expanduser().resolve(),
                output_path=Path(args.output).expanduser().resolve(),
                label=args.label,
            )
            if args.json:
                json.dump(result, sys.stdout, indent=2)
                print()
            else:
                _print_retrieval_record_result(result, Path(args.output).expanduser().resolve())
            return 0

        if args.command == "compare-retrieval":
            result = compare_retrieval_results(
                source_results_path=Path(args.source_results).expanduser().resolve(),
                target_results_path=Path(args.target_results).expanduser().resolve(),
                count_tolerance=args.count_tolerance,
                min_overlap_ratio=args.min_overlap_ratio,
            )
            if args.json:
                json.dump(result, sys.stdout, indent=2)
                print()
            else:
                _print_retrieval_comparison_result(result)
            return 0 if result["valid"] else 1

        if args.command == "record-usage":
            result = record_usage_results(
                palace_path=Path(args.palace).expanduser().resolve(),
                scenarios_path=Path(args.scenarios_file).expanduser().resolve(),
                output_path=Path(args.output).expanduser().resolve(),
                label=args.label,
            )
            if args.json:
                json.dump(result, sys.stdout, indent=2)
                print()
            else:
                _print_usage_record_result(result, Path(args.output).expanduser().resolve())
            return 0

        if args.command == "compare-usage":
            result = compare_usage_results(
                source_results_path=Path(args.source_results).expanduser().resolve(),
                target_results_path=Path(args.target_results).expanduser().resolve(),
                count_tolerance=args.count_tolerance,
                min_overlap_ratio=args.min_overlap_ratio,
            )
            if args.json:
                json.dump(result, sys.stdout, indent=2)
                print()
            else:
                _print_usage_comparison_result(result)
            return 0 if result["valid"] else 1

        if args.command == "validate-mcp-runtime":
            result = validate_mcp_runtime(
                export_dir=Path(args.export_dir).expanduser().resolve(),
                palace_path=Path(args.palace).expanduser().resolve(),
                python_executable=Path(args.python),
                launcher_script=Path(args.launcher_script),
            )
            if args.json:
                json.dump(result, sys.stdout, indent=2)
                print()
            else:
                _print_mcp_runtime_result(result)
            return 0 if result["valid"] else 1

        result = validate_reconstruction(
            export_dir=Path(args.export_dir).expanduser().resolve(),
            target_palace=Path(args.target_palace).expanduser().resolve(),
        )
        if args.json:
            json.dump(result, sys.stdout, indent=2)
            print()
        else:
            _print_validation_result(result)
        return 0 if result["valid"] else 1
    except ReconstructionCliError as exc:
        if args.debug:
            import traceback

            traceback.print_exc(file=sys.stderr)
        else:
            _print_cli_error(exc)
        return 1
    except RuntimeError as exc:
        if args.debug:
            import traceback

            traceback.print_exc(file=sys.stderr)
        else:
            print(f"[ERROR] {exc}", file=sys.stderr)
            print("[INFO]  Run with --debug for full traceback.", file=sys.stderr)
        return 1
    except Exception as exc:
        if args.debug:
            import traceback

            traceback.print_exc(file=sys.stderr)
        else:
            print(f"[ERROR] Unexpected failure: {exc}", file=sys.stderr)
            print("[INFO]  Run with --debug for full traceback.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
