#!/usr/bin/env bash
# scripts/mcp_config.sh
#
# Owns the host-side MCP workspace config (.mcp.json).
#
# The host config must reference the canonical, location-independent bridge path:
#
#     $HOME/.local/share/mempalace-mcp-bridge
#
# and must NEVER reference the physical clone path. The physical clone may live
# anywhere; setup.sh / update.sh create a symlink at the canonical path pointing
# at it (see scripts/link_bridge.sh), and this script writes the MCP config so
# that VS Code / Copilot launch the server through that symlink.
#
# Responsibilities:
#   - generate .mcp.json when it is missing
#   - repair .mcp.json when the stored uv command or --directory path is stale
#   - remove the obsolete .vscode/mcp.json so its stale physical path can never
#     be picked up alongside .mcp.json
#
# Idempotent: a second run rewrites nothing when the config is already correct.
#
# Usage:
#   bash scripts/mcp_config.sh --ensure
#
# Like link_bridge.sh, the repository root is derived from THIS script's own
# location (BASH_SOURCE), never from the caller's working directory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"

CANONICAL_LINK="${HOME}/.local/share/mempalace-mcp-bridge"
MCP_CONFIG="$REPO_ROOT/.mcp.json"
LEGACY_MCP_CONFIG="$REPO_ROOT/.vscode/mcp.json"

info() { echo "[INFO]  $*"; }
ok()   { echo "[OK]    $*"; }
warn() { echo "[WARN]  $*"; }
fail() { echo "[ERROR] $*" >&2; exit 1; }

# Resolve the uv binary the same way the rest of the repo does, without relying
# on a .venv (so this can run before bootstrap and under a fake HOME in tests).
resolve_uv_path() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return 0
    fi
    local candidate
    for candidate in "$HOME/.cargo/bin/uv" "$HOME/.local/bin/uv"; do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

# A python3 interpreter for JSON parsing. Prefer system python3 (available in
# tests and CI), fall back to the repo's own .venv when present.
resolve_json_python() {
    if command -v python3 >/dev/null 2>&1; then
        command -v python3
        return 0
    fi
    if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
        echo "$REPO_ROOT/.venv/bin/python"
        return 0
    fi
    echo "python3"
}

JSON_PYTHON="$(resolve_json_python)"

# Exit 0 when .mcp.json already embeds the canonical bridge path and the
# current uv command; non-zero otherwise.
config_is_current() {
    local uv_path="$1"
    [ -f "$MCP_CONFIG" ] || return 1
    if grep -q "ABSOLUTE/PATH" "$MCP_CONFIG" 2>/dev/null; then
        return 1
    fi
    "$JSON_PYTHON" - "$MCP_CONFIG" "$uv_path" "$CANONICAL_LINK" >/dev/null 2>&1 <<'PYEOF'
import json
import sys

cfg_path, uv_path, canonical = sys.argv[1], sys.argv[2], sys.argv[3]
expected_args = ["run", "--directory", canonical, "python", "scripts/run_mcp_server.py"]
try:
    with open(cfg_path, "r", encoding="utf-8") as handle:
        cfg = json.load(handle)
    server = cfg.get("servers", {}).get("mempalace")
    if not isinstance(server, dict):
        raise SystemExit(1)
    ok = (
        server.get("type") == "stdio"
        and server.get("command") == uv_path
        and server.get("args") == expected_args
    )
    raise SystemExit(0 if ok else 1)
except Exception:
    raise SystemExit(1)
PYEOF
}

generate_config() {
    local uv_path="$1"
    cat > "$MCP_CONFIG" <<EOF
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "$uv_path",
      "args": ["run", "--directory", "$CANONICAL_LINK", "python", "scripts/run_mcp_server.py"]
    }
  }
}
EOF
}

ensure_config() {
    local uv_path
    uv_path="$(resolve_uv_path)" || fail "uv not found — cannot write MCP config."

    if [ -f "$MCP_CONFIG" ] && config_is_current "$uv_path"; then
        ok "MCP config already up to date — not modified ($MCP_CONFIG)"
    else
        if [ -f "$MCP_CONFIG" ]; then
            info "MCP config is stale (wrong uv command or --directory) — regenerating."
        elif [ -f "$LEGACY_MCP_CONFIG" ]; then
            info "Legacy MCP config found at .vscode/mcp.json — consolidating into .mcp.json."
        else
            info "MCP config not found — generating."
        fi
        generate_config "$uv_path"
        ok "MCP config written to $MCP_CONFIG (--directory $CANONICAL_LINK)"
    fi

    # The legacy .vscode/mcp.json is obsolete now that .mcp.json is the source of
    # truth. Remove it so its stale physical clone path can never be picked up.
    if [ -f "$LEGACY_MCP_CONFIG" ]; then
        rm -f "$LEGACY_MCP_CONFIG"
        ok "Removed legacy MCP config ($LEGACY_MCP_CONFIG)"
    fi
}

case "${1:-}" in
    --ensure) ensure_config ;;
    *)
        echo "Usage: $0 --ensure" >&2
        exit 2
        ;;
esac
