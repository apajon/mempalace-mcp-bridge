#!/usr/bin/env bash
# run.sh
# Starts the MemPalace MCP server in stdio mode.
#
# In normal usage VS Code launches this automatically via .vscode/mcp.json.
# Use this script only as a fallback or to test that the server starts correctly.
#
# Keep the terminal open while using Copilot Chat.
# Press Ctrl+C to stop.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$REPO_ROOT/scripts/run_manual_mcp.sh"
