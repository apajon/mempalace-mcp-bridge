#!/usr/bin/env bash
# setup.sh
# One-command setup: installs MemPalace, initializes the palace,
# mines sample data, and writes .mcp.json with the correct uv path.
# Safe to re-run (idempotent).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANONICAL_LINK="${HOME}/.local/share/mempalace-mcp-bridge"

info()  { echo "[INFO]  $*"; }
ok()    { echo "[OK]    $*"; }
fail()  { echo "[ERROR] $*" >&2; exit 1; }

echo "════════════════════════════════════════"
echo " MemPalace MCP Bridge — Setup"
echo "════════════════════════════════════════"
echo ""

# ─── Canonical bridge link ──────────────────────────────────────────────────
# Expose this clone under the stable, location-independent path
# $HOME/.local/share/mempalace-mcp-bridge so consumers never need to know
# where the repo actually lives.

info "Creating canonical bridge link..."
bash "$REPO_ROOT/scripts/link_bridge.sh"

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

# ─── 4. Generate .mcp.json ───────────────────────────────────────────────────

info "Step 4/4 — Generating workspace MCP config..."

# Owns .mcp.json generation/repair (canonical --directory) and removes the
# obsolete .vscode/mcp.json. See scripts/mcp_config.sh.
bash "$REPO_ROOT/scripts/mcp_config.sh" --ensure

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
