#!/usr/bin/env bash
# setup.sh
# One-command setup: installs MemPalace, initializes the palace,
# mines sample data, and writes .vscode/mcp.json with the correct uv path.
# Safe to re-run (idempotent).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

info()  { echo "[INFO]  $*"; }
ok()    { echo "[OK]    $*"; }
fail()  { echo "[ERROR] $*" >&2; exit 1; }

echo "════════════════════════════════════════"
echo " MemPalace MCP Bridge — Setup"
echo "════════════════════════════════════════"
echo ""

# ─── 1. Bootstrap (uv + MemPalace) ───────────────────────────────────────────

info "Step 1/4 — Installing dependencies..."
bash "$REPO_ROOT/scripts/bootstrap.sh"

# ─── 2. Initialize palace ─────────────────────────────────────────────────────

info "Step 2/4 — Initializing MemPalace..."
bash "$REPO_ROOT/scripts/init_palace.sh"

# ─── 2b. Palace health check ──────────────────────────────────────────────────
# Detects and auto-repairs ChromaDB config_json_str incompatibilities that can
# occur after a ChromaDB upgrade. Safe to run on a brand-new palace (no-op).

HEALTH_EXIT=0
bash "$REPO_ROOT/scripts/check_palace_health.sh" || HEALTH_EXIT=$?
# exit 2 means no palace yet (normal here) — not an error
if [ "$HEALTH_EXIT" -eq 1 ]; then
    echo "[ERROR] Palace health check failed — aborting setup." >&2
    exit 1
fi

# ─── 3. Mine sample notes ─────────────────────────────────────────────────────

info "Step 3/4 — Mining sample notes..."
bash "$REPO_ROOT/scripts/mine_sample_data.sh"

# ─── 4. Generate .vscode/mcp.json ─────────────────────────────────────────────

info "Step 4/4 — Generating VS Code MCP config..."

UV_PATH="$(command -v uv 2>/dev/null || true)"
if [ -z "$UV_PATH" ]; then
    # Try common install locations after bootstrap
    for candidate in "$HOME/.cargo/bin/uv" "$HOME/.local/bin/uv"; do
        if [ -x "$candidate" ]; then
            UV_PATH="$candidate"
            break
        fi
    done
fi
[ -n "$UV_PATH" ] || fail "uv not found after bootstrap — cannot write MCP config."

VSCODE_DIR="$REPO_ROOT/.vscode"
MCP_CONFIG="$VSCODE_DIR/mcp.json"

mkdir -p "$VSCODE_DIR"

# Only regenerate if the config is missing, has placeholder paths, or the
# stored paths no longer match this machine (e.g. repo moved, uv reinstalled).
_needs_regen=true
if [ -f "$MCP_CONFIG" ] && ! grep -q "ABSOLUTE/PATH" "$MCP_CONFIG" 2>/dev/null; then
    VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
    _stored_dir=$("$VENV_PYTHON" -c "
import json
try:
    with open('$MCP_CONFIG') as f:
        cfg = json.load(f)
    args = cfg['servers']['mempalace'].get('args', [])
    idx = args.index('--directory') if '--directory' in args else -1
    print(args[idx + 1] if idx >= 0 else '')
except Exception:
    print('')
" 2>/dev/null || true)
    _stored_uv=$("$VENV_PYTHON" -c "
import json
try:
    with open('$MCP_CONFIG') as f:
        cfg = json.load(f)
    print(cfg['servers']['mempalace'].get('command', ''))
except Exception:
    print('')
" 2>/dev/null || true)

    if [ "$_stored_dir" = "$REPO_ROOT" ] && [ "$_stored_uv" = "$UV_PATH" ]; then
        _needs_regen=false
    fi
fi

if [ "$_needs_regen" = true ]; then
    cat > "$MCP_CONFIG" <<EOF
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "$UV_PATH",
      "args": ["run", "--directory", "$REPO_ROOT", "python", "-m", "mempalace.mcp_server"]
    }
  }
}
EOF
    # --directory tells uv which project root to use so it picks up the correct
    # .venv and MemPalace data regardless of where VS Code launches the server.
    ok "MCP config written to $MCP_CONFIG"
else
    ok "MCP config already up to date — not modified ($MCP_CONFIG)"
fi

# ─── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════"
echo " Setup complete!"
echo "════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Open this folder in VS Code"
echo "  2. Open Copilot Chat (Ctrl+Alt+I)"
echo "  3. Ask: \"What architecture decisions have I documented?\""
echo ""
echo "To verify everything works:"
echo "  bash verify.sh"
echo ""
echo "To run the MCP server manually (fallback):"
echo "  bash run.sh"
