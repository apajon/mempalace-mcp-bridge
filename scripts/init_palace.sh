#!/usr/bin/env bash
# scripts/init_palace.sh
# Initializes MemPalace in the current repository workspace.
# Run once per workspace after bootstrap.sh.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
MANIFEST_SCRIPT="$REPO_ROOT/scripts/palace_manifest.py"

info()  { echo "[INFO]  $*"; }
ok()    { echo "[OK]    $*"; }
fail()  { echo "[ERROR] $*" >&2; exit 1; }

# ─── Sanity checks ────────────────────────────────────────────────────────────

if ! command -v uv &>/dev/null; then
    fail "uv not found. Run scripts/bootstrap.sh first."
fi

if [ ! -f "$VENV_PYTHON" ]; then
    fail "Virtual environment not found at $REPO_ROOT/.venv — run scripts/bootstrap.sh first."
fi

# ─── Initialize MemPalace ─────────────────────────────────────────────────────

info "Initializing MemPalace..."

# MemPalace init detects rooms from the project folder structure.
# Palace storage defaults to ~/.mempalace/palace (or path set via --palace).
if ! "$VENV_PYTHON" "$REPO_ROOT/scripts/palace_safety_gate.py" --action create >/dev/null; then
    "$VENV_PYTHON" "$REPO_ROOT/scripts/palace_safety_gate.py" --action create
    exit 1
fi

cd "$REPO_ROOT"
uv run --python "$VENV_PYTHON" mempalace init "$REPO_ROOT"
"$VENV_PYTHON" "$MANIFEST_SCRIPT"

ok "MemPalace initialized"
echo ""
echo "MemPalace palace storage is at:"
echo "  ~/.mempalace/palace    (default — override with --palace flag)"
echo "Manifest:"
echo "  mempalace-bridge-manifest.json"
echo ""
echo "Next:"
echo "  bash scripts/mine_sample_data.sh   # Mine the example notes"
