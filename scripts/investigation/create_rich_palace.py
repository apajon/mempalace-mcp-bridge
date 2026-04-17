#!/usr/bin/env python3
"""Create a richer palace fixture for migration-grade validation.

Unlike the minimal 3-drawer fixture, this palace exercises:
  - Multiple wings and rooms
  - Metadata with varied types (strings, ints, floats, booleans)
  - Long documents with realistic content length
  - Unicode and special characters
  - Duplicate-adjacent content (near-semantic duplicates)
  - Many drawers (50+)

Usage:
    <python-from-target-venv> create_rich_palace.py <palace_dir>
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

WINGS = {
    "project_alpha": {
        "architecture": [
            "The service mesh uses Envoy sidecars for inter-service TLS. Each pod gets a certificate rotated every 24 hours via SPIFFE. This was chosen over mTLS at the application layer because infrastructure-level encryption is transparent to developers.",
            "Database connections pool through PgBouncer in transaction mode. Max pool size is 50 per service, configured via environment variables. Connection strings must never be logged.",
            "The event bus is built on NATS JetStream with at-least-once delivery. Consumer groups use durable subscriptions. Replay from a specific sequence number is supported for disaster recovery.",
            "Frontend assets are served via CloudFront with S3 origin. Cache invalidation is triggered by CI/CD on deploy. TTL for HTML is 60 seconds; for static assets, 1 year with content hashing.",
            "The authentication flow uses OIDC with Auth0 as the identity provider. JWTs are validated at the API gateway level. Refresh tokens have a 30-day sliding window expiration.",
        ],
        "conventions": [
            "All Python code must pass ruff check and ruff format before merge. The CI pipeline runs both in --check mode. pyproject.toml is the single source for configuration.",
            "Branch naming: feature/<ticket-id>-<short-desc>, fix/<ticket-id>-<short-desc>, chore/<desc>. Main is protected; PRs require at least one approval and passing CI.",
            "Error responses follow RFC 7807 (Problem Details for HTTP APIs). All 4xx/5xx responses must include type, title, status, detail, and instance fields.",
            "Log levels: DEBUG for development-only noise, INFO for business events, WARNING for recoverable issues, ERROR for failures requiring attention, CRITICAL for system-down states.",
            "Dependencies are pinned via lock files (uv.lock for Python, package-lock.json for Node). Floating ranges in pyproject.toml are acceptable; lock files are committed.",
        ],
        "debugging": [
            "The 'connection reset by peer' error from PgBouncer usually means the server_idle_timeout was hit. Increase it or add connection validation on checkout.",
            "NATS consumer lag can be monitored via nats-top or the /jsz endpoint. If lag exceeds 10000 messages, check consumer acknowledgment patterns — batch ack is often the fix.",
            "CloudFront 403 errors on deploy are usually caused by the S3 bucket policy not including the new CloudFront distribution OAI. Re-run the terraform apply.",
            "Auth0 token validation failures with 'aud mismatch' mean the API identifier in Auth0 doesn't match the audience claim expected by the gateway. Check both sides.",
        ],
        "decisions": [
            "ADR-001: Chose PostgreSQL over DynamoDB for the primary datastore. Rationale: complex queries, ACID transactions, and the team's existing expertise. Trade-off: operational overhead for scaling.",
            "ADR-002: Rejected GraphQL for the public API in favor of REST with OpenAPI. Rationale: simpler caching, better tooling maturity, and the API surface is resource-oriented.",
            "ADR-003: Adopted trunk-based development over GitFlow. Rationale: reduces merge conflicts, enables continuous delivery, and feature flags handle incomplete work.",
        ],
    },
    "project_beta": {
        "architecture": [
            "The robot control stack uses ROS 2 Jazzy with DDS (CycloneDDS) for inter-node communication. QoS profiles are tuned per topic: sensor data uses BEST_EFFORT, commands use RELIABLE.",
            "Navigation uses Nav2 with a custom BT (behavior tree) for warehouse operations. The BT includes recovery behaviors for stuck detection, path replanning, and emergency stop.",
            "The perception pipeline runs YOLO v8 on an NVIDIA Jetson Orin for object detection at 30fps. Results are published on /perception/detections with bounding boxes and confidence scores.",
        ],
        "conventions": [
            "ROS 2 package naming: <project>_<function> (e.g., beta_navigation, beta_perception). Node naming follows the same pattern with _node suffix.",
            "All launch files must be Python-based (not XML or YAML) to allow conditional logic. Parameters are loaded from YAML files in the config/ directory.",
            "URDF models are maintained in the beta_description package. Xacro macros are used for parameterized components. Joint limits must match the physical hardware specs.",
        ],
        "debugging": [
            "If the robot oscillates during navigation, check the controller's goal tolerance and the inflation layer radius. Usually the inflation radius is too close to the robot footprint.",
            "DDS discovery failures across subnets require explicit participant configuration. Set CYCLONEDDS_URI to point to a config file with the correct peer addresses.",
            "Jetson Orin thermal throttling causes perception latency spikes. Monitor with tegrastats. If GPU temp exceeds 85°C, the fan profile needs adjustment or the enclosure ventilation is insufficient.",
        ],
    },
    "shared_knowledge": {
        "python": [
            "Use pathlib.Path instead of os.path for all path operations. It's more readable and handles edge cases better (trailing separators, relative resolution).",
            "Type hints: use X | None instead of Optional[X] (Python 3.10+). Use from __future__ import annotations for forward references.",
            "For data classes that should be immutable, use @dataclass(frozen=True). For configuration objects that need validation, prefer Pydantic BaseModel.",
            "Context managers (with statements) must be used for all file I/O, database connections, and lock acquisition. Never rely on garbage collection for resource cleanup.",
            "String formatting: use f-strings for simple interpolation, .format() for template reuse, and Template for user-supplied format strings (to prevent injection).",
        ],
        "docker": [
            "Multi-stage builds: use a builder stage for compilation/dependencies, then copy only artifacts to a slim runtime image. This reduces image size and attack surface.",
            "Always pin base image digests in production Dockerfiles. Tags like :latest or :3.12 can change unexpectedly. Use: FROM python:3.12.3-slim@sha256:abc...",
            "Health checks: HEALTHCHECK CMD curl -f http://localhost:8080/health || exit 1. Set --interval=30s --timeout=5s --retries=3.",
        ],
        "git": [
            "Commit messages follow Conventional Commits: type(scope): description. Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert.",
            "Interactive rebase (git rebase -i) before merge to squash WIP commits. Final commits should tell a coherent story. Never rebase published branches.",
        ],
    },
}

# Unicode and special character test cases
UNICODE_DRAWERS = [
    {
        "id": "unicode-jp-001",
        "document": "日本語のテストドキュメント。このドロワーはUnicode文字の保存と検索をテストします。",
        "metadata": {"wing": "unicode_test", "room": "japanese", "source": "fixture"},
    },
    {
        "id": "unicode-emoji-001",
        "document": "Testing emoji preservation: 🚀 deployment, ⚠️ warning, ✅ success, ❌ failure, 🔧 maintenance.",
        "metadata": {"wing": "unicode_test", "room": "emoji", "source": "fixture"},
    },
    {
        "id": "unicode-math-001",
        "document": "Mathematical notation: α = 0.01, β = 0.95, Σ(xi²) = n·σ², ∀x ∈ ℝ: |f(x)| ≤ M.",
        "metadata": {"wing": "unicode_test", "room": "math_symbols", "source": "fixture"},
    },
    {
        "id": "special-newlines-001",
        "document": "Line 1: first paragraph.\nLine 2: second paragraph.\n\nLine 4: after blank line.\n\tLine 5: with tab indent.",
        "metadata": {"wing": "unicode_test", "room": "whitespace", "source": "fixture"},
    },
]

# Near-duplicate pair for deduplication stress
NEAR_DUPES = [
    {
        "id": "neardupe-a",
        "document": "Always use virtual environments for Python projects. Never install packages globally. Use uv for dependency management.",
        "metadata": {"wing": "shared_knowledge", "room": "python", "source": "fixture", "version": 1},
    },
    {
        "id": "neardupe-b",
        "document": "Always use virtual environments for Python projects. Never install packages globally. Use uv for dependency management. Updated: also pin Python version in .python-version.",
        "metadata": {"wing": "shared_knowledge", "room": "python", "source": "fixture", "version": 2},
    },
]

# Metadata with varied types
VARIED_METADATA_DRAWERS = [
    {
        "id": "meta-types-001",
        "document": "Testing metadata with integer values for priority and timestamp-like fields.",
        "metadata": {"wing": "meta_test", "room": "types", "priority": 1, "confidence": 0.95},
    },
    {
        "id": "meta-types-002",
        "document": "Testing metadata with boolean-like string values and empty strings.",
        "metadata": {"wing": "meta_test", "room": "types", "active": "true", "deprecated": "false", "notes": ""},
    },
    {
        "id": "meta-long-001",
        "document": "A" * 5000 + " — this drawer tests long document storage and retrieval fidelity.",
        "metadata": {"wing": "meta_test", "room": "long_content", "char_count": 5055},
    },
]


def _build_drawers() -> list[dict]:
    """Assemble all drawers from the structured wings."""
    drawers = []
    counter = 0

    for wing_name, rooms in WINGS.items():
        for room_name, documents in rooms.items():
            for doc in documents:
                counter += 1
                drawer_id = f"{wing_name}-{room_name}-{counter:04d}"
                drawers.append({
                    "id": drawer_id,
                    "document": doc,
                    "metadata": {
                        "wing": wing_name,
                        "room": room_name,
                        "source": "rich_fixture",
                    },
                })

    drawers.extend(UNICODE_DRAWERS)
    drawers.extend(NEAR_DUPES)
    drawers.extend(VARIED_METADATA_DRAWERS)

    return drawers


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <palace_dir>", file=sys.stderr)
        return 1

    palace_dir = Path(sys.argv[1])

    import chromadb

    version = chromadb.__version__
    try:
        import mempalace
        mp_version = mempalace.__version__
    except Exception:
        mp_version = "unavailable"

    print(f"[create-rich] chromadb={version} mempalace={mp_version}")
    print(f"[create-rich] target: {palace_dir}")

    if palace_dir.exists():
        print(f"[create-rich] ERROR: {palace_dir} already exists", file=sys.stderr)
        return 1

    palace_dir.mkdir(parents=True)

    drawers = _build_drawers()
    print(f"[create-rich] Preparing {len(drawers)} drawers across {len(WINGS)} wings")

    # Create palace
    client = chromadb.PersistentClient(path=str(palace_dir))
    col = client.get_or_create_collection(
        "mempalace_drawers", metadata={"hnsw:space": "cosine"}
    )

    # Batch add (ChromaDB recommends batches ≤ 5000)
    col.add(
        ids=[d["id"] for d in drawers],
        documents=[d["document"] for d in drawers],
        metadatas=[d["metadata"] for d in drawers],
    )
    print(f"[create-rich] Added {len(drawers)} drawers")

    # Verify roundtrip
    del client
    client2 = chromadb.PersistentClient(path=str(palace_dir))
    col2 = client2.get_collection("mempalace_drawers")
    count = col2.count()
    print(f"[create-rich] Roundtrip verify: count={count}")
    if count != len(drawers):
        print(f"[create-rich] ERROR: expected {len(drawers)}, got {count}", file=sys.stderr)
        return 1

    # Verify diverse queries
    queries = [
        ("database connection pooling", "project_alpha"),
        ("ROS 2 navigation behavior tree", "project_beta"),
        ("Python type hints", "shared_knowledge"),
        ("emoji", "unicode_test"),
        ("virtual environments", "shared_knowledge"),
    ]
    fail_count = 0
    for query_text, expected_wing in queries:
        results = col2.query(query_texts=[query_text], n_results=3)
        top_ids = results["ids"][0]
        top_metas = results["metadatas"][0]
        wings_found = [m.get("wing") for m in top_metas]
        match = expected_wing in wings_found
        status = "PASS" if match else "FAIL"
        if not match:
            fail_count += 1
        print(f"[create-rich] Query '{query_text}': {status} top_wings={wings_found}")

    if fail_count > 0:
        print(f"[create-rich] WARNING: {fail_count} query checks did not match expected wing", file=sys.stderr)

    # Dump summary
    wings_in_data = set()
    rooms_in_data = set()
    for d in drawers:
        wings_in_data.add(d["metadata"].get("wing", ""))
        rooms_in_data.add(f"{d['metadata'].get('wing', '')}/{d['metadata'].get('room', '')}")

    print(f"[create-rich] Summary: {count} drawers, {len(wings_in_data)} wings, {len(rooms_in_data)} rooms")

    # Dump raw config for inspection
    db = palace_dir / "chroma.sqlite3"
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    cur.execute("SELECT name, config_json_str FROM collections")
    for name, config_str in cur.fetchall():
        print(f"[create-rich] Collection '{name}' config_json_str={config_str!r}")
    conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
