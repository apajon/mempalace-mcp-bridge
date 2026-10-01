#!/usr/bin/env python3

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mempalace.config import MempalaceConfig


BRIDGE_NAME = "mempalace-mcp-bridge"
MANIFEST_FILENAME = "mempalace-bridge-manifest.json"
MANIFEST_VERSION = 1
STORAGE_BACKEND = "chromadb"
STORAGE_FORMAT = "chromadb-persistent"
COMPATIBILITY_LINE = "chromadb-0.6.x"
REQUIRED_STRING_FIELDS = (
    "bridge",
    "bridge_version",
    "mempalace_version",
    "chromadb_version",
    "python_version",
    "storage_backend",
    "storage_format",
    "compatibility_line",
    "palace_path_source",
    "created_at",
)


def load_bridge_version(repo_root: Path) -> str:
    pyproject_path = repo_root / "pyproject.toml"
    with pyproject_path.open("rb") as handle:
        pyproject = tomllib.load(handle)

    project = pyproject.get("project")
    if not isinstance(project, dict):
        raise RuntimeError(f"missing [project] table in {pyproject_path}")

    version = project.get("version")
    if not isinstance(version, str) or not version:
        raise RuntimeError(f"missing project.version in {pyproject_path}")

    return version


def load_package_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(f"{package_name} is not installed") from exc


def iso_timestamp_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_path_source() -> str:
    if os.environ.get("MEMPALACE_PALACE_PATH"):
        return "env:MEMPALACE_PALACE_PATH"
    return "mempalace-config-or-default"


def detect_palace_storage_profile(palace_path: Path) -> tuple[str, dict[str, int]]:
    """Best-effort structural storage profile of a palace. Never raises."""
    try:
        from palace_legacy_repair import detect_storage_profile
    except Exception:
        return "unknown", {}
    try:
        result = detect_storage_profile(palace_path)
    except Exception:
        return "unknown", {}
    return result.profile, dict(result.schema_versions)


def build_manifest(
    repo_root: Path,
    *,
    storage_profile: str | None = None,
    schema_versions: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build the palace manifest.

    Two distinct notions are recorded and must not be conflated:

    * ``compatibility_line`` — which runtime line this palace is compatible with
      (a *runtime* claim; the stable bridge only opens ``chromadb-0.6.x``);
    * ``storage_profile`` / ``storage_schema_versions`` — what actually wrote the
      SQLite schema (a *provenance* claim).

    For a palace migrated by ChromaDB 1.x and reopened by 0.6.x, the first is
    ``chromadb-0.6.x`` and the second is ``chroma_1_x_migrated`` with
    ``{"sysdb": 10, "metadb": 6, "embeddings_queue": 2}``. Recording only the
    runtime line would be a false provenance claim.
    """
    config = MempalaceConfig()

    if storage_profile is None:
        detected_profile, detected_versions = detect_palace_storage_profile(Path(config.palace_path))
        storage_profile = detected_profile
        if schema_versions is None:
            schema_versions = detected_versions

    return {
        "manifest_version": MANIFEST_VERSION,
        "bridge": BRIDGE_NAME,
        "bridge_version": load_bridge_version(repo_root),
        "mempalace_version": load_package_version("mempalace"),
        "chromadb_version": load_package_version("chromadb"),
        "python_version": platform.python_version(),
        "storage_backend": STORAGE_BACKEND,
        "storage_format": STORAGE_FORMAT,
        "compatibility_line": COMPATIBILITY_LINE,
        "storage_profile": storage_profile or "unknown",
        "storage_schema_versions": dict(schema_versions or {}),
        "collection_name": config.collection_name,
        "palace_path_source": get_path_source(),
        "created_at": iso_timestamp_now(),
    }


def validate_manifest(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "manifest root must be a JSON object"

    if data.get("manifest_version") != MANIFEST_VERSION:
        return f"manifest_version must be {MANIFEST_VERSION}"

    for field_name in REQUIRED_STRING_FIELDS:
        field_value = data.get(field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            return f"{field_name} must be a non-empty string"

    collection_name = data.get("collection_name")
    if collection_name is not None and (not isinstance(collection_name, str) or not collection_name.strip()):
        return "collection_name must be a non-empty string when present"

    # Optional provenance fields (older manifests do not carry them).
    storage_profile = data.get("storage_profile")
    if storage_profile is not None and (
        not isinstance(storage_profile, str) or not storage_profile.strip()
    ):
        return "storage_profile must be a non-empty string when present"

    schema_versions = data.get("storage_schema_versions")
    if schema_versions is not None:
        if not isinstance(schema_versions, dict):
            return "storage_schema_versions must be a JSON object when present"
        for key, value in schema_versions.items():
            if not isinstance(key, str) or not key.strip():
                return "storage_schema_versions keys must be non-empty strings"
            if isinstance(value, bool) or not isinstance(value, int):
                return f"storage_schema_versions[{key!r}] must be an integer"

    try:
        datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
    except ValueError:
        return "created_at must be an ISO 8601 UTC timestamp"

    return None


def load_existing_manifest(manifest_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not manifest_path.exists():
        return None, None

    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON ({exc})"
    except OSError as exc:
        raise RuntimeError(f"could not read {manifest_path}: {exc}") from exc

    error = validate_manifest(data)
    if error is not None:
        return None, error

    return data, None


def write_manifest_file(manifest_path: Path, manifest: dict[str, Any]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=manifest_path.parent,
        prefix=f".{manifest_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(manifest, handle, indent=2, sort_keys=False)
        handle.write("\n")

    temp_path.replace(manifest_path)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    config = MempalaceConfig()
    palace_path = Path(config.palace_path)
    manifest_path = palace_path / MANIFEST_FILENAME

    try:
        existing_manifest, validation_error = load_existing_manifest(manifest_path)
        if existing_manifest is not None:
            print(f"[OK]    Palace manifest already valid at {manifest_path}")
            return 0

        manifest = build_manifest(repo_root)
        write_manifest_file(manifest_path, manifest)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"[ERROR] could not write {manifest_path}: {exc}", file=sys.stderr)
        return 1

    if validation_error is None:
        print(f"[OK]    Palace manifest written to {manifest_path}")
    else:
        print(f"[WARN]  Replaced invalid palace manifest at {manifest_path}: {validation_error}")
        print(f"[OK]    Palace manifest written to {manifest_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
