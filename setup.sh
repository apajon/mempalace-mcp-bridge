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

ok "MCP config written to $MCP_CONFIG"

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
