#!/usr/bin/env bash
# scripts/verify_install.sh
# Verifies that uv, MemPalace, and the sample data are all in place.
# Prints a PASS/FAIL summary.

# Note: -e is intentionally omitted here. This script counts PASS/FAIL
# entries and must continue running even when individual checks fail.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"

PASS=0
FAIL=0

pass() { echo "[PASS] $*"; PASS=$((PASS + 1)); }
fail() { echo "[FAIL] $*"; FAIL=$((FAIL + 1)); }

# ─── 1. uv available ─────────────────────────────────────────────────────────

if command -v uv &>/dev/null; then
    pass "uv found: $(command -v uv) ($(uv --version))"
else
    fail "uv not found in PATH — install it: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

# ─── 2. Virtual environment present ──────────────────────────────────────────

if [ -f "$VENV_PYTHON" ]; then
    pass "Virtual environment found at $REPO_ROOT/.venv"
else
    fail "Virtual environment missing — run scripts/bootstrap.sh"
fi

# ─── 3. MemPalace importable ─────────────────────────────────────────────────

if [ -f "$VENV_PYTHON" ] && "$VENV_PYTHON" -c "import mempalace" 2>/dev/null; then
    pass "mempalace Python package importable"
else
    fail "mempalace not importable — run scripts/bootstrap.sh"
fi

# ─── 4. mempalace CLI responds ───────────────────────────────────────────────

if [ -f "$VENV_PYTHON" ]; then
    if uv run --python "$VENV_PYTHON" mempalace --help &>/dev/null; then
        pass "mempalace CLI responds (--help)"
    elif "$REPO_ROOT/.venv/bin/mempalace" --help &>/dev/null; then
        pass "mempalace CLI responds (direct bin)"
    else
        fail "mempalace CLI did not respond — check installation"
    fi
fi

# ─── 5. Sample notes present ─────────────────────────────────────────────────

NOTES_DIR="$REPO_ROOT/examples/sample_notes"
if [ -d "$NOTES_DIR" ] && ls "$NOTES_DIR"/*.md &>/dev/null; then
    NOTE_COUNT=$(ls "$NOTES_DIR"/*.md | wc -l)
    pass "Sample notes found in examples/sample_notes/ ($NOTE_COUNT files)"
else
    fail "Sample notes missing in $NOTES_DIR"
fi

# ─── 6. MCP config example present ──────────────────────────────────────────

if [ -f "$REPO_ROOT/examples/mcp/vscode.mcp.json" ]; then
    pass "MCP config example found at examples/mcp/vscode.mcp.json"
else
    fail "MCP config example missing"
fi

# ─── Summary ─────────────────────────────────────────────────────────────────

echo ""
echo "─────────────────────────────────────────"
if [ "$FAIL" -eq 0 ]; then
    echo " All $PASS checks passed."
else
    echo " $PASS passed, $FAIL failed."
    echo " Fix the failures above and re-run this script."
fi
echo "─────────────────────────────────────────"

[ "$FAIL" -eq 0 ]
