#!/usr/bin/env bash
# verify.sh
# Verifies the full MemPalace MCP setup: uv, MemPalace, sample data,
# VS Code MCP config, and — crucially — that the exact command VS Code will
# run actually starts without error.
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
    if uv run --python "$VENV_PYTHON" mempalace --help &>/dev/null; then
        pass "mempalace CLI responds"
    elif "$REPO_ROOT/.venv/bin/mempalace" --help &>/dev/null; then
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

# ─── 7. MCP server actually starts (runs the exact command VS Code will use) ─
#
# Parse command + args from .vscode/mcp.json, start the process with stdin
# held open, wait 2 seconds, verify the process is still running, then kill it.
# This closes the gap between "env is OK" and "Copilot will actually connect".

if [ -f "$VENV_PYTHON" ] && [ -f "$MCP_CONFIG" ]; then
    MCP_LAUNCH=$("$VENV_PYTHON" -c "
import json
with open('$MCP_CONFIG') as f:
    cfg = json.load(f)
srv = cfg['servers']['mempalace']
print(srv['command'])
for a in srv.get('args', []):
    print(a)
" 2>/dev/null)

    if [ -z "$MCP_LAUNCH" ]; then
        fail "Could not parse MCP command from $MCP_CONFIG"
    else
        readarray -t MCP_PARTS <<< "$MCP_LAUNCH"
        MCP_COMMAND="${MCP_PARTS[0]}"
        MCP_ARGS=("${MCP_PARTS[@]:1}")

        # Start server with stdin kept open for 5 s (mirrors how VS Code holds it)
        "${MCP_COMMAND}" "${MCP_ARGS[@]}" < <(sleep 5) &>/dev/null &
        SERVER_PID=$!
        sleep 2

        if kill -0 "$SERVER_PID" 2>/dev/null; then
            pass "MCP server starts without error (exact command from .vscode/mcp.json)"
            kill "$SERVER_PID" 2>/dev/null
            wait "$SERVER_PID" 2>/dev/null || true
        else
            fail "MCP server exited immediately — run: bash run.sh to diagnose"
        fi
    fi
fi

# ─── 8. Palace health check — ChromaDB compatibility ────────────────────────
#
# Delegates to scripts/check_palace_health.sh which detects the known
# version-mismatch bug (config_json_str missing _type) and auto-repairs it.

if [ -f "$VENV_PYTHON" ] && "$VENV_PYTHON" -c "import mempalace" 2>/dev/null; then
    HEALTH_EXIT=0
    HEALTH_OUTPUT=$(bash "$REPO_ROOT/scripts/check_palace_health.sh" 2>&1) || HEALTH_EXIT=$?

    if [ "$HEALTH_EXIT" -eq 0 ]; then
        # Extract the message after [OK] or [WARN] for display
        if echo "$HEALTH_OUTPUT" | grep -q "\[WARN\]"; then
            echo "$HEALTH_OUTPUT"
            pass "Palace auto-repaired and accessible"
        else
            DRAWER_COUNT=$(echo "$HEALTH_OUTPUT" | grep -oP '\d+ drawers' | grep -oP '\d+' || true)
            pass "Palace accessible${DRAWER_COUNT:+ ($DRAWER_COUNT drawers)}"
        fi
    elif [ "$HEALTH_EXIT" -eq 2 ]; then
        echo "[INFO]  Palace not yet initialized — skipping health check"
    else
        echo "$HEALTH_OUTPUT"
        fail "Palace not accessible — see docs/troubleshooting.md#chromadb-version-incompatibility"
    fi
fi

# ─── 9. MemPalace version staleness check (best effort, never blocks) ────────
#
# Query PyPI for the latest published version and compare it to the locally
# installed one.  A version mismatch is shown as a warning only — it does not
# count as a FAIL so that users behind a firewall or without internet are
# not penalised.

if [ -f "$VENV_PYTHON" ] && "$VENV_PYTHON" -c "import mempalace" 2>/dev/null; then
    LOCAL_VER=$("$VENV_PYTHON" -c "
import importlib.metadata, sys
try:
    print(importlib.metadata.version('mempalace'))
except Exception:
    print('')
" 2>/dev/null || true)

    if [ -n "$LOCAL_VER" ]; then
        LATEST_VER=$(curl -fsSL --max-time 5 "https://pypi.org/pypi/mempalace/json" 2>/dev/null \
            | "$VENV_PYTHON" -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d['info']['version'])
except Exception:
    print('')
" 2>/dev/null || true)

        if [ -n "$LATEST_VER" ] && [ "$LOCAL_VER" != "$LATEST_VER" ]; then
            echo "[WARN]  Your MemPalace version may be outdated: installed=$LOCAL_VER, latest=$LATEST_VER"
            echo "        Consider running: bash update.sh"
        elif [ -n "$LATEST_VER" ]; then
            pass "MemPalace is up to date (version $LOCAL_VER)"
        else
            pass "MemPalace installed (version $LOCAL_VER, could not check for updates)"
        fi
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

