#!/usr/bin/env bash
# tests/test_script_wiring.sh
#
# Contract tests for how setup.sh and update.sh drive
# scripts/runtime_aliases.sh, without ever running setup.sh / update.sh
# themselves (they would upgrade packages and touch the real machine).
#
# Contract:
#   setup.sh   -> an interactive install MAY prompt for sudo (mode auto)
#   update.sh  -> must NEVER prompt; a required root privilege is an error that
#                 points the operator at setup.sh
#
# Nothing here touches the real /opt, /mempalace, $HOME or a palace: the runtime
# roots live under a temporary directory and a fake `sudo` that always fails is
# first on PATH, so a real password prompt is impossible.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_SCRIPT="$REPO_ROOT/scripts/runtime_aliases.sh"
LINK_SCRIPT="$REPO_ROOT/scripts/link_bridge.sh"
SETUP_SH="$REPO_ROOT/setup.sh"
UPDATE_SH="$REPO_ROOT/update.sh"

PASS=0
FAIL=0
pass() { echo "[PASS] $*"; PASS=$((PASS + 1)); }
fail() { echo "[FAIL] $*"; FAIL=$((FAIL + 1)); }

TMP="$(mktemp -d)"
trap 'chmod -R u+rwX "$TMP" 2>/dev/null || true; rm -rf "$TMP"' EXIT

# ─── Fake sudo that can never succeed and never prompts ───────────────────────
JAIL="$TMP/jail"
SUDO_LOG="$TMP/sudo.log"
mkdir -p "$JAIL"
: > "$SUDO_LOG"
cat > "$JAIL/sudo" <<'JAILSCRIPT'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${SUDO_LOG:?SUDO_LOG must be set}"
exit 1
JAILSCRIPT
chmod +x "$JAIL/sudo"

# ─── Helpers to read the mode a script actually uses ─────────────────────────

# Prints the runtime_aliases.sh option (if any) used by a shell script.
extract_flag() {
    local script="$1"
    local line
    line="$(grep -F 'runtime_aliases.sh' "$script" | grep -vE '^[[:space:]]*#' | head -1)"
    printf '%s' "$line" | grep -oE '\-\-[a-zA-Z][a-zA-Z=+-]*' | head -1
}

# Normalises an option into a SUDO_MODE value (empty means the default, auto).
normalise_mode() {
    case "${1:-}" in
        "") echo "auto" ;;
        --no-sudo) echo "diagnose" ;;
        --sudo=*) echo "${1#--sudo=}" ;;
        --*) echo "${1#--}" ;;
        *) echo "$1" ;;
    esac
}

SETUP_FLAG="$(extract_flag "$SETUP_SH")"
UPDATE_FLAG="$(extract_flag "$UPDATE_SH")"
SETUP_MODE="$(normalise_mode "$SETUP_FLAG")"
UPDATE_MODE="$(normalise_mode "$UPDATE_FLAG")"

echo "== A: setup.sh uses the interactive-capable mode =="
if grep -qF 'runtime_aliases.sh' "$SETUP_SH"; then
    pass "setup.sh invokes runtime_aliases.sh"
else
    fail "setup.sh invokes runtime_aliases.sh"
fi
if [ "$SETUP_MODE" = "auto" ] || [ "$SETUP_MODE" = "interactive" ]; then
    pass "setup.sh may prompt for sudo (mode: $SETUP_MODE)"
else
    fail "setup.sh may prompt for sudo (mode: $SETUP_MODE)"
fi

echo "== B: update.sh uses a mode that can never prompt =="
if grep -qF 'runtime_aliases.sh' "$UPDATE_SH"; then
    pass "update.sh invokes runtime_aliases.sh"
else
    fail "update.sh invokes runtime_aliases.sh"
fi
case "$UPDATE_MODE" in
    diagnose|non-interactive)
        pass "update.sh uses a non-prompting mode (mode: $UPDATE_MODE)"
        ;;
    *)
        fail "update.sh uses a non-prompting mode (mode: $UPDATE_MODE)"
        ;;
esac
if grep -qE -- '--interactive|--sudo=interactive' "$UPDATE_SH"; then
    fail "update.sh must never request an interactive sudo mode"
else
    pass "update.sh never requests an interactive sudo mode"
fi

echo "== C: update.sh's mode never escalates interactively on a fresh host =="
if [ "$(id -u)" -eq 0 ]; then
    echo "[SKIP] running as root — the privilege predicate is trivially satisfied"
else
    FAKE_HOME="$TMP/home"
    FAKE_REPO="$TMP/repo"
    mkdir -p "$FAKE_HOME" "$FAKE_REPO/scripts"
    cp "$RUNTIME_SCRIPT" "$FAKE_REPO/scripts/runtime_aliases.sh"
    cp "$LINK_SCRIPT" "$FAKE_REPO/scripts/link_bridge.sh"
    printf 'name = "mempalace-mcp-bridge"\n' > "$FAKE_REPO/pyproject.toml"
    (cd "$TMP" && HOME="$FAKE_HOME" bash "$FAKE_REPO/scripts/link_bridge.sh") >/dev/null 2>&1

    # /opt-like and /-like: existing ancestors the user cannot write to.
    HOST_SIM="$TMP/host"
    rm -rf "$HOST_SIM"
    mkdir -p "$HOST_SIM/opt"
    chmod 555 "$HOST_SIM" "$HOST_SIM/opt"
    HOST_BRIDGE="$HOST_SIM/opt/mempalace-mcp-bridge"
    HOST_PALACE="$HOST_SIM/mempalace"

    : > "$SUDO_LOG"
    OUT_C="$(cd "$TMP" && HOME="$FAKE_HOME" PATH="$JAIL:$PATH" \
        SUDO_LOG="$SUDO_LOG" \
        MEMPALACE_RUNTIME_BRIDGE_PATH="$HOST_BRIDGE" \
        MEMPALACE_RUNTIME_PALACE_ROOT="$HOST_PALACE" \
        bash "$FAKE_REPO/scripts/runtime_aliases.sh" "--sudo=$UPDATE_MODE" </dev/null 2>&1)"
    STATUS_C=$?
    chmod 755 "$HOST_SIM" "$HOST_SIM/opt" 2>/dev/null || true

    if [ "$STATUS_C" -ne 0 ]; then
        pass "update.sh's mode fails instead of escalating"
    else
        fail "update.sh's mode fails instead of escalating"
    fi
    if grep -qv -- '^-n ' "$SUDO_LOG" 2>/dev/null; then
        fail "update.sh's mode must never invoke sudo without -n (no prompt)"
    else
        pass "update.sh's mode never invokes sudo without -n (no prompt possible)"
    fi
    if [ ! -e "$HOST_BRIDGE" ] && [ ! -e "$HOST_PALACE" ]; then
        pass "nothing was partially created"
    else
        fail "nothing was partially created"
    fi
    if printf '%s' "$OUT_C" | grep -q "setup.sh"; then
        pass "the failure tells the operator to run setup.sh"
    else
        fail "the failure tells the operator to run setup.sh"
    fi
fi

echo ""
echo "─────────────────────────────────────────"
echo " $PASS passed, $FAIL failed."
echo "─────────────────────────────────────────"

[ "$FAIL" -eq 0 ]
