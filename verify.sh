#!/usr/bin/env bash
# verify.sh
# Verifies the full MemPalace MCP setup: uv, MemPalace, sample data,
# and VS Code MCP config.
# Prints a PASS/FAIL summary and exits non-zero if any check fails.

# Note: -e is intentionally omitted. This script must continue running
# even when individual checks fail so that all results are shown.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"

PASS=0
FAIL=0

pass() { echo "[PASS] $*"; PASS=$((PASS + 1)); }
fail() { echo "[FAIL] $*"; FAIL=$((FAIL + 1)); }

echo "════════════════════════════════════════"
echo " MemPalace MCP Bridge — Verify"
echo "════════════════════════════════════════"
echo ""

# ─── 1. uv available ─────────────────────────────────────────────────────────

if command -v uv &>/dev/null; then
    pass "uv found: $(command -v uv) ($(uv --version))"
else
    fail "uv not found in PATH — run: bash setup.sh"
fi

# ─── 2. Virtual environment present ──────────────────────────────────────────

if [ -f "$VENV_PYTHON" ]; then
    pass "Virtual environment found at .venv/"
else
    fail "Virtual environment missing — run: bash setup.sh"
fi

# ─── 3. MemPalace importable ─────────────────────────────────────────────────

if [ -f "$VENV_PYTHON" ] && "$VENV_PYTHON" -c "import mempalace" 2>/dev/null; then
    pass "mempalace package importable"
else
    fail "mempalace not importable — run: bash setup.sh"
fi

# ─── 4. mempalace CLI responds ───────────────────────────────────────────────

if [ -f "$VENV_PYTHON" ]; then
    if uv run --python "$VENV_PYTHON" mempalace --help &>/dev/null 2>&1; then
        pass "mempalace CLI responds"
    elif "$REPO_ROOT/.venv/bin/mempalace" --help &>/dev/null 2>&1; then
        pass "mempalace CLI responds"
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

# ─── 6. VS Code MCP config exists and has correct content ───────────────────

MCP_CONFIG="$REPO_ROOT/.vscode/mcp.json"
if [ -f "$MCP_CONFIG" ]; then
    if grep -q "mempalace" "$MCP_CONFIG" && ! grep -q "ABSOLUTE/PATH" "$MCP_CONFIG"; then
        pass "VS Code MCP config present and populated ($MCP_CONFIG)"
    else
        fail "VS Code MCP config still has placeholder paths — run: bash setup.sh"
    fi
else
    fail "VS Code MCP config missing — run: bash setup.sh"
fi

# ─── 7. MCP server starts ────────────────────────────────────────────────────

if [ -f "$VENV_PYTHON" ]; then
    if timeout 5 uv run --python "$VENV_PYTHON" python -c "import mempalace.mcp_server" 2>/dev/null; then
        pass "mempalace.mcp_server module importable"
    else
        fail "mempalace.mcp_server module not importable — check installation"
    fi
fi

# ─── Summary ─────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════"
if [ "$FAIL" -eq 0 ]; then
    echo " All $PASS checks passed — you're ready to use MemPalace in VS Code!"
else
    echo " $PASS passed, $FAIL failed."
    echo " Fix the failures above and re-run: bash verify.sh"
fi
echo "════════════════════════════════════════"

[ "$FAIL" -eq 0 ]
