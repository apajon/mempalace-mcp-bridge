#!/usr/bin/env bash
# scripts/mine_sample_data.sh
# Mines the example notes in examples/sample_notes/ into MemPalace.
# Run after init_palace.sh.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
NOTES_DIR="$REPO_ROOT/examples/sample_notes"

info()  { echo "[INFO]  $*"; }
ok()    { echo "[OK]    $*"; }
fail()  { echo "[ERROR] $*" >&2; exit 1; }

# ─── Sanity checks ────────────────────────────────────────────────────────────

if ! command -v uv &>/dev/null; then
    fail "uv not found. Run scripts/bootstrap.sh first."
fi

if [ ! -f "$VENV_PYTHON" ]; then
    fail "Virtual environment not found — run scripts/bootstrap.sh first."
fi

if [ ! -d "$NOTES_DIR" ]; then
    fail "Sample notes directory not found: $NOTES_DIR"
fi

# ─── Mine files ───────────────────────────────────────────────────────────────

info "Mining files from $REPO_ROOT ..."

cd "$REPO_ROOT"
uv run --python "$VENV_PYTHON" mempalace mine "$REPO_ROOT"

ok "Mining complete"
echo ""
echo "Sample notes mined from:"
ls "$NOTES_DIR"/*.md 2>/dev/null | while read -r f; do echo "  - examples/sample_notes/$(basename "$f")"; done
echo ""
echo "To verify memory was indexed:"
echo "  uv run --python $VENV_PYTHON mempalace search \"architecture\""
echo ""
echo "To mine your own notes later:"
echo "  uv run --python $VENV_PYTHON mempalace mine /path/to/your/project/"
