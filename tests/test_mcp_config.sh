#!/usr/bin/env bash
# tests/test_mcp_config.sh
#
# Exercises scripts/mcp_config.sh against a temporary HOME and a fake repo.
# Never touches the developer's real HOME, real clone, or palace data.
#
# Covers the universal host/DevContainer MCP config contract:
#   A. arbitrary clone dir -> .mcp.json uses the runtime path and 'uv', never
#                             the physical clone path, and sets the palace env
#   B. second run           -> idempotent, no rewrite
#   C. stale physical path  -> repaired to the runtime path
#   D. legacy .vscode/mcp.json -> removed, .mcp.json canonical
#   E. unrelated servers/keys preserved
#   F. missing mempalace insertion preserves unrelated content
#   G. correct config + unrelated content -> no rewrite
#   H. legacy launcher / uv / palace path forms migrated
#   I. output JSON stays valid
#   J. unrelated keys inside the mempalace entry preserved

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCP_CONFIG_SCRIPT="$REPO_ROOT/scripts/mcp_config.sh"
LINK_SCRIPT="$REPO_ROOT/scripts/link_bridge.sh"

PASS=0
FAIL=0
pass() { echo "[PASS] $*"; PASS=$((PASS + 1)); }
fail() { echo "[FAIL] $*"; FAIL=$((FAIL + 1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAKE_HOME="$TMP/home"
# Deliberately NOT named "mempalace-mcp-bridge" to prove location independence.
FAKE_REPO="$TMP/repos/some-random-clone-location"
mkdir -p "$FAKE_HOME" "$FAKE_REPO/scripts" "$FAKE_REPO/.vscode"
cp "$MCP_CONFIG_SCRIPT" "$FAKE_REPO/scripts/mcp_config.sh"
cp "$LINK_SCRIPT" "$FAKE_REPO/scripts/link_bridge.sh"
printf 'name = "mempalace-mcp-bridge"\n' > "$FAKE_REPO/pyproject.toml"

# A fake uv under the fake HOME (used to build legacy configs).
FAKE_UV="$FAKE_HOME/.local/bin/uv"
mkdir -p "$(dirname "$FAKE_UV")"
printf '#!/usr/bin/env bash\nexit 0\n' > "$FAKE_UV"
chmod +x "$FAKE_UV"

LINK="$FAKE_HOME/.local/share/mempalace-mcp-bridge"
CANONICAL_DIR="$FAKE_HOME/.local/share/mempalace-mcp-bridge"
EXPECTED_TARGET="$(cd "$FAKE_REPO" && pwd -P)"

# Runtime overrides so the test never needs root. These are the same env seams
# scripts/runtime_aliases.sh and scripts/mcp_config.sh expose for testing.
RUNTIME_BRIDGE="$TMP/opt/mempalace-mcp-bridge"
RUNTIME_PALACE="$TMP/mempalace/palace"

run_link() {
    (cd "$TMP" && HOME="$FAKE_HOME" bash "$FAKE_REPO/scripts/link_bridge.sh" "${1:-}") >/dev/null 2>&1
}
run_ensure() {
    (cd "$TMP" && HOME="$FAKE_HOME" PATH="$FAKE_HOME/.local/bin:$PATH" \
        MEMPALACE_RUNTIME_BRIDGE_PATH="$RUNTIME_BRIDGE" \
        MEMPALACE_RUNTIME_PALACE_PATH="$RUNTIME_PALACE" \
        bash "$FAKE_REPO/scripts/mcp_config.sh" --ensure)
}

# json_check <label> <python-bool-expr> — evaluate an expression against the
# current .mcp.json, with `d` bound to the whole object and `s` to `servers`.
json_check() {
    local label="$1" expr="$2"
    if python3 -c "import json,sys; d=json.load(open('$FAKE_REPO/.mcp.json')); s=d.get('servers',{}); sys.exit(0 if ($expr) else 1)" 2>/dev/null; then
        pass "$label"
    else
        fail "$label"
    fi
}

echo "== A: arbitrary clone -> universal runtime config =="
run_link ""
if [ -L "$LINK" ] && [ "$(readlink "$LINK")" = "$EXPECTED_TARGET" ]; then
    pass "canonical symlink points to the arbitrary clone"
else
    fail "canonical symlink points to the arbitrary clone"
fi

run_ensure >/dev/null 2>&1
if [ -f "$FAKE_REPO/.mcp.json" ]; then pass ".mcp.json generated"; else fail ".mcp.json generated"; fi

if grep -Fq "$RUNTIME_BRIDGE" "$FAKE_REPO/.mcp.json" 2>/dev/null; then
    pass ".mcp.json contains the universal runtime bridge path"
else
    fail ".mcp.json contains the universal runtime bridge path"
fi

json_check "launcher command is 'uv'" "s.get('mempalace', {}).get('command') == 'uv'"
json_check "palace env is set to the runtime palace path" "s.get('mempalace', {}).get('env', {}).get('MEMPALACE_PALACE_PATH') == '$RUNTIME_PALACE'"

if grep -Fq "$EXPECTED_TARGET" "$FAKE_REPO/.mcp.json" 2>/dev/null; then
    fail ".mcp.json must NOT contain the physical clone path"
else
    pass ".mcp.json does NOT contain the physical clone path"
fi

if grep -Fq "$CANONICAL_DIR" "$FAKE_REPO/.mcp.json" 2>/dev/null; then
    fail ".mcp.json must NOT contain the user-specific canonical link"
else
    pass ".mcp.json does NOT contain the user-specific canonical link"
fi

echo "== B: idempotent second run =="
CONTENT_BEFORE="$(cat "$FAKE_REPO/.mcp.json")"
OUT_B="$(run_ensure 2>&1)"
CONTENT_AFTER="$(cat "$FAKE_REPO/.mcp.json")"
if [ "$CONTENT_BEFORE" = "$CONTENT_AFTER" ]; then
    pass "second run leaves .mcp.json byte-identical"
else
    fail "second run leaves .mcp.json byte-identical"
fi
if printf '%s' "$OUT_B" | grep -q "already up to date"; then
    pass "second run reports up to date"
else
    fail "second run reports up to date"
fi

echo "== C: stale physical path -> repaired =="
printf '{"servers":{"mempalace":{"type":"stdio","command":"%s","args":["run","--directory","%s","python","scripts/run_mcp_server.py"]}}}\n' \
    "$FAKE_UV" "$EXPECTED_TARGET" > "$FAKE_REPO/.mcp.json"
run_ensure >/dev/null 2>&1
if grep -Fq "$RUNTIME_BRIDGE" "$FAKE_REPO/.mcp.json" 2>/dev/null && ! grep -Fq "$EXPECTED_TARGET" "$FAKE_REPO/.mcp.json" 2>/dev/null; then
    pass "stale physical path repaired to the runtime path"
else
    fail "stale physical path repaired to the runtime path"
fi

echo "== D: legacy .vscode/mcp.json removed =="
printf '{"servers":{"mempalace":{"type":"stdio","command":"%s","args":["run","--directory","%s","python","scripts/run_mcp_server.py"]}}}\n' \
    "$FAKE_UV" "$EXPECTED_TARGET" > "$FAKE_REPO/.vscode/mcp.json"
run_ensure >/dev/null 2>&1
if [ ! -e "$FAKE_REPO/.vscode/mcp.json" ]; then
    pass "legacy .vscode/mcp.json removed"
else
    fail "legacy .vscode/mcp.json removed"
fi
if grep -Fq "$RUNTIME_BRIDGE" "$FAKE_REPO/.mcp.json" 2>/dev/null && ! grep -Fq "$EXPECTED_TARGET" "$FAKE_REPO/.mcp.json" 2>/dev/null; then
    pass ".mcp.json canonical after legacy removal"
else
    fail ".mcp.json canonical after legacy removal"
fi

echo "== E: stale mempalace repair preserves unrelated servers/keys =="
cat > "$FAKE_REPO/.mcp.json" <<EOF
{
  "extra_top_level": {"nested": [1, 2, 3]},
  "servers": {
    "mempalace": {
      "command": "$FAKE_UV",
      "args": ["run", "--directory", "$EXPECTED_TARGET", "python", "scripts/run_mcp_server.py"]
    },
    "github": {"command": "some-command", "args": ["foo"]},
    "custom-company-server": {"command": "another-command"}
  }
}
EOF
run_ensure >/dev/null 2>&1
if grep -Fq "$RUNTIME_BRIDGE" "$FAKE_REPO/.mcp.json" 2>/dev/null && ! grep -Fq "$EXPECTED_TARGET" "$FAKE_REPO/.mcp.json" 2>/dev/null; then
    pass "mempalace repaired to the runtime path, physical path removed"
else
    fail "mempalace repaired to the runtime path, physical path removed"
fi
json_check "github server preserved" "s.get('github', {}).get('command') == 'some-command' and s.get('github', {}).get('args') == ['foo']"
json_check "custom-company-server preserved" "s.get('custom-company-server', {}).get('command') == 'another-command'"
json_check "unrelated top-level key preserved" "d.get('extra_top_level') == {'nested': [1, 2, 3]}"

echo "== F: missing mempalace insertion preserves unrelated content =="
cat > "$FAKE_REPO/.mcp.json" <<EOF
{
  "servers": {
    "github": {"command": "some-command", "args": ["foo"]},
    "custom-company-server": {"command": "another-command"}
  },
  "top_level_note": "keep me"
}
EOF
run_ensure >/dev/null 2>&1
if grep -Fq "$RUNTIME_BRIDGE" "$FAKE_REPO/.mcp.json" 2>/dev/null; then
    pass "mempalace inserted with the runtime path"
else
    fail "mempalace inserted with the runtime path"
fi
json_check "github preserved after insertion" "s.get('github', {}).get('command') == 'some-command'"
json_check "custom-company-server preserved after insertion" "s.get('custom-company-server', {}).get('command') == 'another-command'"
json_check "top-level key preserved after insertion" "d.get('top_level_note') == 'keep me'"

echo "== G: correct mempalace + unrelated content -> no rewrite =="
CONTENT_BEFORE="$(cat "$FAKE_REPO/.mcp.json")"
OUT_G="$(run_ensure 2>&1)"
CONTENT_AFTER="$(cat "$FAKE_REPO/.mcp.json")"
if [ "$CONTENT_BEFORE" = "$CONTENT_AFTER" ]; then
    pass "second run with extra servers leaves file byte-identical"
else
    fail "second run with extra servers leaves file byte-identical"
fi
if printf '%s' "$OUT_G" | grep -q "already up to date"; then
    pass "second run reports up to date"
else
    fail "second run reports up to date"
fi

echo "== H: legacy launcher / uv command / palace env migrated =="
cat > "$FAKE_REPO/.mcp.json" <<EOF
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "$FAKE_UV",
      "args": ["run", "--directory", "$CANONICAL_DIR", "python", "-m", "mempalace.mcp_server"],
      "env": {"MEMPALACE_PALACE_PATH": "$FAKE_HOME/.mempalace/palace", "EXTRA_KEEP": "1"}
    }
  }
}
EOF
run_ensure >/dev/null 2>&1
json_check "legacy absolute uv command migrated to 'uv'" "s['mempalace'].get('command') == 'uv'"
json_check "legacy 'python -m mempalace.mcp_server' launcher migrated" "s['mempalace'].get('args') == ['run', '--directory', '$RUNTIME_BRIDGE', 'python', 'scripts/run_mcp_server.py']"
json_check "legacy palace path migrated" "s['mempalace'].get('env', {}).get('MEMPALACE_PALACE_PATH') == '$RUNTIME_PALACE'"
json_check "unrelated env key preserved inside mempalace" "s['mempalace'].get('env', {}).get('EXTRA_KEEP') == '1'"

echo "== I: output JSON stays valid =="
if python3 -c "import json; json.load(open('$FAKE_REPO/.mcp.json'))" 2>/dev/null; then
    pass ".mcp.json is valid JSON"
else
    fail ".mcp.json is valid JSON"
fi

echo "== J: unrelated keys inside the mempalace entry preserved =="
cat > "$FAKE_REPO/.mcp.json" <<EOF
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "$RUNTIME_BRIDGE", "python", "scripts/run_mcp_server.py"],
      "env": {"MEMPALACE_PALACE_PATH": "$RUNTIME_PALACE"},
      "disabled": false,
      "autoApprove": ["search"]
    }
  }
}
EOF
CONTENT_J_BEFORE="$(cat "$FAKE_REPO/.mcp.json")"
run_ensure >/dev/null 2>&1
CONTENT_J_AFTER="$(cat "$FAKE_REPO/.mcp.json")"
if [ "$CONTENT_J_BEFORE" = "$CONTENT_J_AFTER" ]; then
    pass "entry with unknown keys stays byte-identical"
else
    fail "entry with unknown keys stays byte-identical"
fi
json_check "disabled key preserved" "s['mempalace'].get('disabled') is False"
json_check "autoApprove key preserved" "s['mempalace'].get('autoApprove') == ['search']"

echo ""
echo "─────────────────────────────────────────"
echo " $PASS passed, $FAIL failed."
echo "─────────────────────────────────────────"

[ "$FAIL" -eq 0 ]
