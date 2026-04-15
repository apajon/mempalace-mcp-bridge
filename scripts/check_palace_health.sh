#!/usr/bin/env bash
# scripts/check_palace_health.sh
# Detects ChromaDB config_json_str incompatibilities and can auto-repair them.
#
# Background: ChromaDB >= 0.6.0 requires a _type field in config_json_str.
# Palaces created with older versions store '{}' and fail with "No palace found".
# This script can either report the problem or, in repair mode, back up the SQLite
# file and apply the fix in-place.
#
# Exit codes:
#   0 — palace is healthy (or was successfully repaired)
#   1 — palace is inaccessible and could not be repaired
#   2 — palace not found (no SQLite yet — normal after a fresh install)
#
# Callers: setup.sh, update.sh, verify.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
MODE="repair"

case "${1:-}" in
    ""|--repair)
        ;;
    --read-only)
        MODE="read-only"
        ;;
    *)
        echo "[FAIL]  Unknown option: ${1}" >&2
        echo "        Use --repair or --read-only." >&2
        exit 1
        ;;
esac

warn()  { echo "[WARN]  $*"; }
ok()    { echo "[OK]    $*"; }
fail_msg() { echo "[FAIL]  $*" >&2; }

if [ ! -f "$VENV_PYTHON" ]; then
    fail_msg "Virtual environment not found — run: bash setup.sh"
    exit 1
fi

RESULT=$(
PALACE_HEALTH_MODE="$MODE" "$VENV_PYTHON" - 2>/dev/null <<'PYEOF'
import sys, json, sqlite3, shutil
import os
from pathlib import Path

try:
    from mempalace.config import MempalaceConfig
    import chromadb
    from chromadb.api.configuration import CollectionConfigurationInternal
except ImportError as e:
    print(f"SKIP:{e}")
    sys.exit(0)

cfg = MempalaceConfig()
palace_path = cfg.palace_path
db_path = Path(palace_path) / "chroma.sqlite3"
mode = os.environ.get("PALACE_HEALTH_MODE", "repair")

if not db_path.exists():
    print("NOTFOUND:")
    sys.exit(0)

# ── Step 1: detect broken config_json_str ────────────────────────────────────
conn = sqlite3.connect(str(db_path))
c = conn.cursor()
try:
    c.execute("SELECT id, name, config_json_str FROM collections")
    rows = c.fetchall()
except Exception as e:
    print(f"FAIL:{e}")
    conn.close()
    sys.exit(1)

broken = [(row[0], row[1]) for row in rows if not json.loads(row[2] or "{}").get("_type")]

if broken:
    if mode == "read-only":
        print(f"BROKEN:{','.join(name for _, name in broken)}")
        conn.close()
        sys.exit(1)

    # Back up the SQLite before any modification
    backup_path = str(db_path) + ".bak"
    shutil.copy2(str(db_path), backup_path)
    correct = CollectionConfigurationInternal().to_json_str()
    fixed_names = []
    for col_id, col_name in broken:
        c.execute("UPDATE collections SET config_json_str = ? WHERE id = ?", (correct, col_id))
        fixed_names.append(col_name)
    conn.commit()
    conn.close()
    print(f"FIXED:{','.join(fixed_names)}")
    sys.exit(0)

conn.close()

# ── Step 2: connectivity test ─────────────────────────────────────────────────
try:
    client = chromadb.PersistentClient(path=palace_path)
    col = client.get_or_create_collection(cfg.collection_name)
    print(f"OK:{col.count()}")
except Exception as e:
    print(f"FAIL:{e}")
    sys.exit(1)
PYEOF
)

case "$RESULT" in
    OK:*)
        ok "Palace healthy (${RESULT#OK:} drawers)"
        exit 0
        ;;
    FIXED:*)
        NAMES="${RESULT#FIXED:}"
        warn "ChromaDB config incompatibility detected on collection(s): $NAMES"
        warn "Auto-repaired. Backup saved as: ~/.mempalace/palace/chroma.sqlite3.bak"
        warn "See docs/troubleshooting.md#chromadb-version-incompatibility for details."
        ok "Palace repaired and accessible"
        exit 0
        ;;
    BROKEN:*)
        NAMES="${RESULT#BROKEN:}"
        fail_msg "Palace has a ChromaDB config incompatibility on collection(s): $NAMES"
        fail_msg "Run: bash update.sh"
        fail_msg "See docs/troubleshooting.md#chromadb-version-incompatibility"
        exit 1
        ;;
    NOTFOUND:*)
        # Normal during a fresh install before init_palace.sh
        exit 2
        ;;
    SKIP:*)
        # mempalace not yet importable — bootstrap not done
        exit 2
        ;;
    FAIL:*)
        fail_msg "Palace not accessible: ${RESULT#FAIL:}"
        fail_msg "See docs/troubleshooting.md#chromadb-version-incompatibility"
        exit 1
        ;;
    *)
        fail_msg "Unexpected palace check result: $RESULT"
        exit 1
        ;;
esac
