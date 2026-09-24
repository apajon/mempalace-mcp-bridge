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
#   - repair only servers.mempalace when its uv command or --directory path is
#     stale, preserving every other server and top-level key
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

# Updates only .servers.mempalace in .mcp.json, preserving every other
# top-level key and every unrelated server. The read-modify-write happens in
# Python so unrelated content survives untouched, and the file is written
# atomically (temp file + rename) only when the mempalace entry actually needs
# to change.
#
# Prints exactly one token on stdout:
#   current  -> .mcp.json already correct, nothing written
#   created  -> .mcp.json did not exist, created with servers.mempalace
#   updated  -> only servers.mempalace was inserted/replaced, all else preserved
#   invalid  -> .mcp.json exists but is not valid JSON, left untouched (error)
update_config() {
    local uv_path="$1"
    "$JSON_PYTHON" - "$MCP_CONFIG" "$uv_path" "$CANONICAL_LINK" <<'PYEOF'
import json
import os
import sys
import tempfile

cfg_path, uv_path, canonical = sys.argv[1], sys.argv[2], sys.argv[3]

expected_entry = {
    "type": "stdio",
    "command": uv_path,
    "args": ["run", "--directory", canonical, "python", "scripts/run_mcp_server.py"],
}

created = not os.path.exists(cfg_path)

if created:
    cfg = {}
else:
    try:
        with open(cfg_path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except OSError:
        print("invalid")
        raise SystemExit(1)

    if not raw.strip():
        cfg = {}
    else:
        try:
            cfg = json.loads(raw)
        except Exception:
            print("invalid")
            raise SystemExit(1)

if not isinstance(cfg, dict):
    cfg = {}

servers = cfg.get("servers")
if not isinstance(servers, dict):
    servers = {}
    cfg["servers"] = servers

# Only the mempalace entry is owned; everything else is preserved verbatim.
if not created and servers.get("mempalace") == expected_entry:
    print("current")
    raise SystemExit(0)

servers["mempalace"] = expected_entry

# Preserve the original file mode when present, defaulting to 0o644.
mode = None
if not created:
    try:
        mode = os.stat(cfg_path).st_mode & 0o777
    except OSError:
        mode = None

parent = os.path.dirname(os.path.abspath(cfg_path)) or "."
fd, tmp_path = tempfile.mkstemp(dir=parent, prefix=".mcp.json.", suffix=".tmp")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp_path, mode if mode is not None else 0o644)
    os.replace(tmp_path, cfg_path)
finally:
    try:
        os.remove(tmp_path)
    except OSError:
        pass

print("created" if created else "updated")
PYEOF
}

ensure_config() {
    local uv_path
    uv_path="$(resolve_uv_path)" || fail "uv not found — cannot write MCP config."

    local result
    if ! result="$(update_config "$uv_path" 2>&1)"; then
        echo "[ERROR] Could not update MCP config (left untouched):" >&2
        echo "$result" >&2
        exit 1
    fi

    case "$result" in
        current) ok "MCP config already up to date — not modified ($MCP_CONFIG)" ;;
        created) ok "MCP config written to $MCP_CONFIG (--directory $CANONICAL_LINK)" ;;
        updated) ok "MCP config repaired — only servers.mempalace updated ($MCP_CONFIG)" ;;
        *) warn "$result" ;;
    esac

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
