#!/usr/bin/env bash
# tests/test_mcp_config.sh
#
# Exercises scripts/mcp_config.sh against a temporary HOME and a fake repo.
# Never touches the developer's real HOME, real clone, or palace data.
#
# Covers the host MCP config path contract:
#   A. arbitrary clone dir  -> canonical symlink + .mcp.json uses the canonical
#                              path and never the physical clone path
#   B. second run           -> idempotent, no rewrite
#   C. stale physical path  -> repaired to the canonical path
#   D. legacy .vscode/mcp.json -> removed, .mcp.json canonical

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

# A fake uv under the fake HOME so resolve_uv_path() finds an absolute path.
FAKE_UV="$FAKE_HOME/.local/bin/uv"
mkdir -p "$(dirname "$FAKE_UV")"
printf '#!/usr/bin/env bash\nexit 0\n' > "$FAKE_UV"
chmod +x "$FAKE_UV"

LINK="$FAKE_HOME/.local/share/mempalace-mcp-bridge"
CANONICAL_DIR="$FAKE_HOME/.local/share/mempalace-mcp-bridge"
EXPECTED_TARGET="$(cd "$FAKE_REPO" && pwd -P)"

run_link() {
    (cd "$TMP" && HOME="$FAKE_HOME" bash "$FAKE_REPO/scripts/link_bridge.sh" "${1:-}") >/dev/null 2>&1
}
run_ensure() {
    (cd "$TMP" && HOME="$FAKE_HOME" PATH="$FAKE_HOME/.local/bin:$PATH" bash "$FAKE_REPO/scripts/mcp_config.sh" --ensure)
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

echo "== A: arbitrary clone -> canonical path in .mcp.json =="
run_link ""
if [ -L "$LINK" ] && [ "$(readlink "$LINK")" = "$EXPECTED_TARGET" ]; then
    pass "canonical symlink points to the arbitrary clone"
else
    fail "canonical symlink points to the arbitrary clone"
fi

run_ensure >/dev/null 2>&1
if [ -f "$FAKE_REPO/.mcp.json" ]; then pass ".mcp.json generated"; else fail ".mcp.json generated"; fi

if grep -Fq "$CANONICAL_DIR" "$FAKE_REPO/.mcp.json" 2>/dev/null; then
    pass ".mcp.json contains the canonical path"
else
    fail ".mcp.json contains the canonical path"
fi

if grep -Fq "$EXPECTED_TARGET" "$FAKE_REPO/.mcp.json" 2>/dev/null; then
    fail ".mcp.json must NOT contain the physical clone path"
else
    pass ".mcp.json does NOT contain the physical clone path"
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
if grep -Fq "$CANONICAL_DIR" "$FAKE_REPO/.mcp.json" 2>/dev/null && ! grep -Fq "$EXPECTED_TARGET" "$FAKE_REPO/.mcp.json" 2>/dev/null; then
    pass "stale physical path repaired to canonical"
else
    fail "stale physical path repaired to canonical"
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
if grep -Fq "$CANONICAL_DIR" "$FAKE_REPO/.mcp.json" 2>/dev/null && ! grep -Fq "$EXPECTED_TARGET" "$FAKE_REPO/.mcp.json" 2>/dev/null; then
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
if grep -Fq "$CANONICAL_DIR" "$FAKE_REPO/.mcp.json" 2>/dev/null && ! grep -Fq "$EXPECTED_TARGET" "$FAKE_REPO/.mcp.json" 2>/dev/null; then
    pass "mempalace repaired to canonical, physical path removed"
else
    fail "mempalace repaired to canonical, physical path removed"
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
if grep -Fq "$CANONICAL_DIR" "$FAKE_REPO/.mcp.json" 2>/dev/null; then
    pass "mempalace inserted with canonical path"
else
    fail "mempalace inserted with canonical path"
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

echo ""
echo "─────────────────────────────────────────"
echo " $PASS passed, $FAIL failed."
echo "─────────────────────────────────────────"

[ "$FAIL" -eq 0 ]
