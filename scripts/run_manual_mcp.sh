#!/usr/bin/env bash
# scripts/run_manual_mcp.sh
# Fallback: manually launches the MemPalace MCP server in stdio mode.
#
# Use this only if auto-start via your MCP client config is not working.
# In normal usage, the MCP client (VS Code, etc.) starts this automatically.
#
# Keep this terminal open while using the chat client.
# Press Ctrl+C to stop the server.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"

fail() { echo "[ERROR] $*" >&2; exit 1; }

if ! command -v uv &>/dev/null; then
    fail "uv not found. Run scripts/bootstrap.sh first."
fi

if [ ! -f "$VENV_PYTHON" ]; then
    fail "Virtual environment not found — run scripts/bootstrap.sh first."
fi

echo "[INFO]  Starting MemPalace MCP server (stdio mode)..."
echo "[INFO]  Press Ctrl+C to stop."
echo ""

cd "$REPO_ROOT"
exec uv run --python "$VENV_PYTHON" python -m mempalace.mcp_server
