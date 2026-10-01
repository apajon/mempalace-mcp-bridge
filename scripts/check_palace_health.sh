#!/usr/bin/env bash
# scripts/check_palace_health.sh
# Detects ChromaDB config_json_str incompatibilities and can auto-repair them.
#
# Background: ChromaDB >= 0.6.0 requires a _type field in config_json_str.
# Palaces created with older versions store '{}' and fail with "No palace found".
#
# This script is a thin, policy-enforcing wrapper:
#   1. it asks the safety gate whether the requested action is authorised
#      (read-only -> "read", repair -> "repair");
#   2. it delegates the actual check/repair to scripts/palace_legacy_repair.py,
#      which owns the strict legacy invariants, the non-overwriting SQLite
#      backup (via the SQLite backup API) and the post-repair smoke test.
#
# A legacy palace is only auto-repaired when it matches the narrow legacy
# contract. Any other unrecognised palace is refused untouched.
#
# Exit codes:
#   0 — palace is healthy (or was successfully repaired)
#   1 — palace is inaccessible, refused, or could not be repaired
#   2 — palace not found (no SQLite yet) or not bootstrapped — normal after a
#       fresh install
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

GATE_ACTION="repair"
if [ "$MODE" = "read-only" ]; then
    GATE_ACTION="read"
fi

GATE_OUTPUT=""
GATE_EXIT=0
GATE_OUTPUT=$("$VENV_PYTHON" "$REPO_ROOT/scripts/palace_safety_gate.py" --action "$GATE_ACTION" 2>&1) || GATE_EXIT=$?
if [ "$GATE_EXIT" -ne 0 ]; then
    # In read-only mode, tell the operator precisely whether this is a
    # repairable legacy palace or genuinely unsafe storage.
    if [ "$MODE" = "read-only" ]; then
        if "$VENV_PYTHON" "$REPO_ROOT/scripts/palace_legacy_repair.py" >/dev/null 2>&1; then
            fail_msg "Palace is a legacy palace that requires the narrow repair (untyped config)."
            fail_msg "Run: bash update.sh"
            fail_msg "Or:  python3 scripts/palace_legacy_repair.py <palace> --apply"
            exit 1
        fi
    fi
    printf '%s\n' "$GATE_OUTPUT" >&2
    exit 1
fi

# The gate authorised the operation. Delegate the actual health check / narrow
# legacy repair to palace_legacy_repair.py, which owns the strict invariants,
# the non-overwriting SQLite backup and the post-repair smoke test.
RESULT="$("$VENV_PYTHON" "$REPO_ROOT/scripts/palace_legacy_repair.py" --health "$MODE")" || true

case "$RESULT" in
    OK:*)
        ok "Palace healthy (${RESULT#OK:} drawers)"
        exit 0
        ;;
    FIXED:*)
        FIXED_PAYLOAD="${RESULT#FIXED:}"
        FIXED_NAMES="${FIXED_PAYLOAD%%|*}"
        FIXED_BACKUP="${FIXED_PAYLOAD#*|}"
        warn "ChromaDB legacy config detected on collection(s): $FIXED_NAMES"
        warn "Narrow legacy repair applied. Backup: ${FIXED_BACKUP:-<not reported>}"
        warn "See docs/troubleshooting.md#chromadb-version-incompatibility for details."
        ok "Palace repaired and accessible"
        exit 0
        ;;
    REPAIRABLE:*)
        fail_msg "Palace is a legacy palace that requires the narrow repair (untyped config)."
        fail_msg "Collections: ${RESULT#REPAIRABLE:}"
        fail_msg "Run: bash update.sh"
        fail_msg "Or:  python3 scripts/palace_legacy_repair.py <palace> --apply"
        exit 1
        ;;
    UNKNOWN:*)
        fail_msg "Palace format is unknown and does not match the narrow legacy repair contract."
        fail_msg "${RESULT#UNKNOWN:}"
        fail_msg "Refusing to mutate this palace. Inspect it with: python3 scripts/palace_format_detector.py <palace> --pretty"
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
