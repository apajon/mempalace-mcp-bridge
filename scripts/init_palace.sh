#!/usr/bin/env bash
# scripts/init_palace.sh
# Initializes MemPalace in the current repository workspace.
# Run once per workspace after bootstrap.sh.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"

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

# MemPalace stores its data locally (default: ~/.mempalace/ or a path set during init).
# We run init from the repo root so any relative config picks up the workspace.
cd "$REPO_ROOT"
uv run --python "$VENV_PYTHON" mempalace init

ok "MemPalace initialized"
echo ""
echo "MemPalace memory data is stored in:"
echo "  ~/.mempalace/    (default location — check mempalace docs for custom paths)"
echo ""
echo "Next:"
echo "  bash scripts/mine_sample_data.sh   # Mine the example notes"
