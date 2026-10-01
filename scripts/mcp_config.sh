#!/usr/bin/env bash
# scripts/mcp_config.sh
#
# Owns the host-side MCP workspace config (.mcp.json).
#
# The config must be identical on the host and inside the DevContainer, so it
# must not embed any user-specific path. It converges to the universal config:
#
#     command: "uv"
#     args:    ["run", "--directory", "/opt/mempalace-mcp-bridge",
#               "python", "scripts/run_mcp_server.py"]
#     env:     {"MEMPALACE_PALACE_PATH": "/mempalace/palace"}
#
# `/opt/mempalace-mcp-bridge` and `/mempalace` are runtime aliases owned by
# scripts/runtime_aliases.sh (on the host) and by bind mounts (in the
# DevContainer). The physical clone may live anywhere and the palace stays
# host-owned under $HOME/.mempalace.
#
# Responsibilities:
#   - generate .mcp.json when it is missing
#   - repair only servers.mempalace when it diverges, preserving every other
#     server, every unrelated top-level key, and unrelated keys inside the
#     mempalace entry itself
#   - migrate the known legacy shapes: absolute uv command, canonical-link or
#     physical-clone --directory, `python -m mempalace.mcp_server` launcher,
#     missing/old MEMPALACE_PALACE_PATH
#   - remove the obsolete .vscode/mcp.json so its stale path can never be
#     picked up alongside .mcp.json
#
# Idempotent: a second run rewrites nothing when the config is already correct.
#
# Usage:
#   bash scripts/mcp_config.sh --ensure
#
# Like link_bridge.sh, the repository root is derived from THIS script's own
# location (BASH_SOURCE), never from the caller's working directory.
#
# Testing / override seams (not part of the user-facing contract):
#   MEMPALACE_RUNTIME_BRIDGE_PATH  (default /opt/mempalace-mcp-bridge)
#   MEMPALACE_RUNTIME_PALACE_PATH  (default /mempalace/palace)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"

RUNTIME_BRIDGE_PATH="${MEMPALACE_RUNTIME_BRIDGE_PATH:-/opt/mempalace-mcp-bridge}"
RUNTIME_PALACE_PATH="${MEMPALACE_RUNTIME_PALACE_PATH:-/mempalace/palace}"

MCP_CONFIG="$REPO_ROOT/.mcp.json"
LEGACY_MCP_CONFIG="$REPO_ROOT/.vscode/mcp.json"

info() { echo "[INFO]  $*"; }
ok()   { echo "[OK]    $*"; }
warn() { echo "[WARN]  $*"; }
fail() { echo "[ERROR] $*" >&2; exit 1; }

# Warns when the launcher cannot be resolved by the MCP client. The config
# deliberately does not embed a uv path (it must stay portable), so this is a
# warning rather than a hard failure.
check_uv_on_path() {
    if command -v uv >/dev/null 2>&1; then
        return 0
    fi
    for candidate in "$HOME/.cargo/bin/uv" "$HOME/.local/bin/uv"; do
        [ -x "$candidate" ] && return 0
    done
    warn "uv was not found on PATH — the MCP client must be able to resolve 'uv'."
    warn "Install it (https://astral.sh/uv) or make sure it is on the client's PATH."
    return 0
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
# top-level key, every unrelated server, and unrelated keys inside the
# mempalace entry. The read-modify-write happens in Python so unrelated content
# survives untouched, and the file is written atomically (temp file + rename)
# only when the mempalace entry actually needs to change.
#
# Prints exactly one token on stdout:
#   current  -> .mcp.json already correct, nothing written
#   created  -> .mcp.json did not exist, created with servers.mempalace
#   updated  -> only servers.mempalace was inserted/replaced, all else preserved
#   invalid  -> .mcp.json exists but is not valid JSON, left untouched (error)
update_config() {
    "$JSON_PYTHON" - "$MCP_CONFIG" "$RUNTIME_BRIDGE_PATH" "$RUNTIME_PALACE_PATH" <<'PYEOF'
import json
import os
import sys
import tempfile

cfg_path, runtime_bridge, runtime_palace = sys.argv[1], sys.argv[2], sys.argv[3]

expected_args = ["run", "--directory", runtime_bridge, "python", "scripts/run_mcp_server.py"]

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

existing = servers.get("mempalace")
if not isinstance(existing, dict):
    existing = {}

# Rebuild only the fields this script owns, preserving any other key a user may
# have added inside the mempalace entry (e.g. "disabled", "autoApprove").
merged = dict(existing)
merged["type"] = "stdio"
merged["command"] = "uv"
merged["args"] = expected_args

env = merged.get("env")
env = dict(env) if isinstance(env, dict) else {}
env["MEMPALACE_PALACE_PATH"] = runtime_palace
merged["env"] = env

if not created and existing == merged:
    print("current")
    raise SystemExit(0)

servers["mempalace"] = merged

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
    check_uv_on_path

    local result
    if ! result="$(update_config 2>&1)"; then
        echo "[ERROR] Could not update MCP config (left untouched):" >&2
        echo "$result" >&2
        exit 1
    fi

    case "$result" in
        current) ok "MCP config already up to date — not modified ($MCP_CONFIG)" ;;
        created) ok "MCP config written to $MCP_CONFIG (--directory $RUNTIME_BRIDGE_PATH)" ;;
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
