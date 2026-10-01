#!/usr/bin/env bash
# tests/test_runtime_aliases.sh
#
# Exercises scripts/runtime_aliases.sh against a temporary HOME and temporary
# runtime roots. Never touches the developer's real HOME, /opt, /mempalace, the
# real clone, or palace data.
#
# Covers the universal runtime alias contract:
#   A. both aliases absent             -> created
#   B. run twice                       -> idempotent, symlinks unchanged
#   C. broken symlink                  -> repaired
#   D. symlink to an old location      -> re-pointed, old target left intact
#   E. alias path is a real directory  -> fatal, directory untouched
#   F. alias path is a regular file    -> fatal, file untouched
#   G. palace data is never deleted    -> sentinel survives every operation
#   H. unwritable parent, no sudo      -> explicit diagnostic, non-zero exit
#   I. --status reports a wrong target
#   J. correct aliases                 -> no-op even in interactive sudo mode
#   K. --sudo=interactive without TTY  -> hard error, no partial mutation
#   L. --sudo=non-interactive          -> succeeds when no privilege is needed
#   M. real-directory conflict         -> nothing at all is created elsewhere
#   N. --print-manual / invalid mode   -> usage contract
#   O. genuinely-needed privilege      -> escalated through the (jailed) sudo
#   P. fresh standard Linux host       -> /opt-like and /-like parents are not
#                                         writable; diagnose refuses, a real PTY
#                                         selects the interactive sudo path, a
#                                         non-interactive mode never prompts
#
# A fake `sudo` is placed first on PATH for every invocation, so these tests can
# never reach the real, password-protected sudo: they cannot prompt and cannot
# hang. Several cases additionally assert that sudo was NOT invoked.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_SCRIPT="$REPO_ROOT/scripts/runtime_aliases.sh"
LINK_SCRIPT="$REPO_ROOT/scripts/link_bridge.sh"

PASS=0
FAIL=0
pass() { echo "[PASS] $*"; PASS=$((PASS + 1)); }
fail() { echo "[FAIL] $*"; FAIL=$((FAIL + 1)); }

TMP="$(mktemp -d)"
trap 'chmod -R u+rwX "$TMP" 2>/dev/null || true; rm -rf "$TMP"' EXIT

# ─── sudo jail ────────────────────────────────────────────────────────────────
# A test double for `sudo` is placed first on PATH so these tests can NEVER reach
# the real, password-protected sudo. It records every invocation and performs the
# requested operation after granting write access to the relevant parent, which
# lets the privileged code path be exercised without root and without a prompt.
SUDO_JAIL="$TMP/jail"
SUDO_LOG="$TMP/sudo.log"
mkdir -p "$SUDO_JAIL"
: > "$SUDO_LOG"
cat > "$SUDO_JAIL/sudo" <<'JAIL'
#!/usr/bin/env bash
set -uo pipefail
printf '%s\n' "$*" >> "${SUDO_LOG:?SUDO_LOG must be set}"
args=("$@")
if [ "${args[0]:-}" = "-n" ]; then
    if [ "${args[1]:-}" = "true" ]; then
        # Emulate a host where passwordless sudo is (0) or is not (1) available.
        exit "${SUDO_JAIL_NOPASSWD:-0}"
    fi
    args=("${args[@]:1}")
fi
cmd="${args[0]:-}"
rest=("${args[@]:1}")
case "$cmd" in
    true)
        exit 0
        ;;
    mkdir)
        [ "${rest[0]:-}" = "-p" ] && rest=("${rest[@]:1}")
        [ "${rest[0]:-}" = "--" ] && rest=("${rest[@]:1}")
        target="${rest[0]}"
        parent="$(dirname -- "$target")"
        [ -d "$parent" ] && chmod u+w -- "$parent" 2>/dev/null
        mkdir -p -- "$target"
        ;;
    ln)
        [ "${rest[0]:-}" = "-s" ] && rest=("${rest[@]:1}")
        [ "${rest[0]:-}" = "--" ] && rest=("${rest[@]:1}")
        chmod u+w -- "$(dirname -- "${rest[1]}")" 2>/dev/null
        ln -s -- "${rest[0]}" "${rest[1]}"
        ;;
    rm)
        [ "${rest[0]:-}" = "-f" ] && rest=("${rest[@]:1}")
        [ "${rest[0]:-}" = "--" ] && rest=("${rest[@]:1}")
        chmod u+w -- "$(dirname -- "${rest[0]}")" 2>/dev/null
        rm -f -- "${rest[0]}"
        ;;
    *)
        exit 1
        ;;
esac
JAIL
chmod +x "$SUDO_JAIL/sudo"

reset_sudo_log() { : > "$SUDO_LOG"; }
sudo_was_called() { [ -s "$SUDO_LOG" ]; }
bare_sudo_was_called() { grep -qv -- '^-n ' "$SUDO_LOG" 2>/dev/null; }

# ─── Fresh standard Linux host simulation ─────────────────────────────────────
# On a fresh host the runtime roots live under an existing ancestor the user
# cannot write to: `/opt` for the bridge and `/` for the palace. A non-writable
# *existing* ancestor is exactly the predicate the script evaluates, including
# its walk up to the nearest existing ancestor, so this reproduces the real
# semantics rather than just using a writable temporary directory.
HOST_SIM="$TMP/host"
HOST_BRIDGE="$HOST_SIM/opt/mempalace-mcp-bridge"
HOST_PALACE="$HOST_SIM/mempalace"
HOST_SUDO_MODE="diagnose"
HOST_NOPASSWD="0"

fresh_host() {
    host_sim_unlocked
    rm -rf "$HOST_SIM"
    mkdir -p "$HOST_SIM/opt"
    chmod 555 "$HOST_SIM" "$HOST_SIM/opt"
}

host_sim_unlocked() {
    chmod 755 "$HOST_SIM" "$HOST_SIM/opt" 2>/dev/null || true
}

run_host_sim() {
    (cd "$TMP" && HOME="$FAKE_HOME" PATH="$SUDO_JAIL:$PATH" \
        SUDO_LOG="$SUDO_LOG" \
        MEMPALACE_RUNTIME_BRIDGE_PATH="$HOST_BRIDGE" \
        MEMPALACE_RUNTIME_PALACE_ROOT="$HOST_PALACE" \
        MEMPALACE_RUNTIME_SUDO="$HOST_SUDO_MODE" \
        SUDO_JAIL_NOPASSWD="$HOST_NOPASSWD" \
        bash "$FAKE_REPO/scripts/runtime_aliases.sh" "--sudo=$HOST_SUDO_MODE") </dev/null
}

# Same, but under a real PTY allocated by util-linux `script`, so it is the
# script's own `[ -t 0 ]` test that selects the interactive path.
run_host_sim_tty() {
    local wrapper="$TMP/host-tty.sh"
    cat > "$wrapper" <<WRAPPER
#!/usr/bin/env bash
cd "$TMP" || exit 1
export HOME="$FAKE_HOME"
export PATH="$SUDO_JAIL:\$PATH"
export SUDO_LOG="$SUDO_LOG"
export MEMPALACE_RUNTIME_BRIDGE_PATH="$HOST_BRIDGE"
export MEMPALACE_RUNTIME_PALACE_ROOT="$HOST_PALACE"
export MEMPALACE_RUNTIME_SUDO=interactive
export SUDO_JAIL_NOPASSWD=0
exec bash "$FAKE_REPO/scripts/runtime_aliases.sh" --sudo=interactive
WRAPPER
    chmod +x "$wrapper"
    script -qec "$wrapper" /dev/null
}

FAKE_HOME="$TMP/home"
FAKE_REPO="$TMP/repos/some-random-clone-location"
OLD_REPO="$TMP/repos/old-mempalace-mcp-bridge"

mkdir -p "$FAKE_HOME" "$FAKE_REPO/scripts" "$OLD_REPO"
cp "$RUNTIME_SCRIPT" "$FAKE_REPO/scripts/runtime_aliases.sh"
cp "$LINK_SCRIPT" "$FAKE_REPO/scripts/link_bridge.sh"
printf 'name = "mempalace-mcp-bridge"\n' > "$FAKE_REPO/pyproject.toml"
printf 'name = "old-clone"\n' > "$OLD_REPO/pyproject.toml"

CANONICAL_LINK="$FAKE_HOME/.local/share/mempalace-mcp-bridge"
PALACE_HOME="$FAKE_HOME/.mempalace"
RUNTIME_BRIDGE="$TMP/opt/mempalace-mcp-bridge"
RUNTIME_PALACE_ROOT="$TMP/mempalace"

EXPECTED_TARGET="$(cd "$FAKE_REPO" && pwd -P)"
OLD_TARGET="$(cd "$OLD_REPO" && pwd -P)"

# Runs the alias script with a temporary HOME, temporary runtime roots and sudo
# disabled. Never runs inside the fake repo. The sudo jail is always first on
# PATH, so the real sudo can never be reached.
run_runtime() {
    (cd "$TMP" && HOME="$FAKE_HOME" PATH="$SUDO_JAIL:$PATH" \
        SUDO_LOG="$SUDO_LOG" \
        MEMPALACE_RUNTIME_BRIDGE_PATH="$RUNTIME_BRIDGE" \
        MEMPALACE_RUNTIME_PALACE_ROOT="$RUNTIME_PALACE_ROOT" \
        MEMPALACE_RUNTIME_ALLOW_SUDO=0 \
        bash "$FAKE_REPO/scripts/runtime_aliases.sh" "${1:-}") </dev/null
}

ensure_canonical_link() {
    (cd "$TMP" && HOME="$FAKE_HOME" bash "$FAKE_REPO/scripts/link_bridge.sh") >/dev/null 2>&1
}

# Runs the alias script with the default (auto) sudo policy but with stdin
# detached from any terminal. Safe for cases where no privilege is required.
run_auto() {
    (cd "$TMP" && HOME="$FAKE_HOME" PATH="$SUDO_JAIL:$PATH" \
        SUDO_LOG="$SUDO_LOG" \
        MEMPALACE_RUNTIME_BRIDGE_PATH="$RUNTIME_BRIDGE" \
        MEMPALACE_RUNTIME_PALACE_ROOT="$RUNTIME_PALACE_ROOT" \
        bash "$FAKE_REPO/scripts/runtime_aliases.sh" "$@") </dev/null
}

# Same, but `never` by default so a test can never escalate for real. Explicit
# flags still win, which lets the mode-specific tests below run safely: an
# unwritable parent plus no TTY means the privilege check fails before any
# mutation is attempted, whatever the host's sudo configuration is.
run_policy() {
    (cd "$TMP" && HOME="$FAKE_HOME" PATH="$SUDO_JAIL:$PATH" \
        SUDO_LOG="$SUDO_LOG" \
        MEMPALACE_RUNTIME_BRIDGE_PATH="$RUNTIME_BRIDGE" \
        MEMPALACE_RUNTIME_PALACE_ROOT="$RUNTIME_PALACE_ROOT" \
        MEMPALACE_RUNTIME_SUDO=never \
        bash "$FAKE_REPO/scripts/runtime_aliases.sh" "$@") </dev/null
}

reset_aliases() {
    rm -rf "$TMP/opt" "$TMP/mempalace" "$FAKE_HOME/.local" "$FAKE_HOME/.mempalace"
}

echo "== A: both aliases absent -> created (no privileges needed) =="
reset_aliases
ensure_canonical_link
reset_sudo_log
if run_runtime "" >/dev/null 2>&1; then pass "ensure exits 0"; else fail "ensure exits 0"; fi
if sudo_was_called; then
    fail "writable parents must not require sudo"
else
    pass "writable parents do not require sudo"
fi
if [ -L "$RUNTIME_BRIDGE" ]; then pass "bridge runtime alias is a symlink"; else fail "bridge runtime alias is a symlink"; fi
if [ -L "$RUNTIME_BRIDGE" ] && [ "$(readlink "$RUNTIME_BRIDGE")" = "$CANONICAL_LINK" ]; then
    pass "bridge runtime alias points at the canonical link"
else
    fail "bridge runtime alias points at the canonical link (got '$(readlink "$RUNTIME_BRIDGE" 2>/dev/null || true)')"
fi
if [ "$(readlink -f "$RUNTIME_BRIDGE" 2>/dev/null || true)" = "$EXPECTED_TARGET" ]; then
    pass "bridge runtime alias resolves to the real clone"
else
    fail "bridge runtime alias resolves to the real clone"
fi
if [ -L "$RUNTIME_PALACE_ROOT" ] && [ "$(readlink "$RUNTIME_PALACE_ROOT")" = "$PALACE_HOME" ]; then
    pass "palace runtime alias points at the palace home"
else
    fail "palace runtime alias points at the palace home"
fi
if [ "$(readlink -f "$RUNTIME_PALACE_ROOT/palace" 2>/dev/null || true)" = "$(cd "$PALACE_HOME" && pwd -P)/palace" ]; then
    pass "palace runtime alias resolves <alias>/palace to the host palace"
else
    fail "palace runtime alias resolves <alias>/palace to the host palace"
fi
if [ -d "$PALACE_HOME" ]; then pass "palace home directory was created"; else fail "palace home directory was created"; fi

echo "== B: run twice -> idempotent =="
BRIDGE_LINK_BEFORE="$(readlink "$RUNTIME_BRIDGE")"
PALACE_LINK_BEFORE="$(readlink "$RUNTIME_PALACE_ROOT")"
OUT_B="$(run_runtime "" 2>&1)"
if [ $? -eq 0 ]; then pass "second run exits 0"; else fail "second run exits 0"; fi
if [ "$(readlink "$RUNTIME_BRIDGE")" = "$BRIDGE_LINK_BEFORE" ] && [ "$(readlink "$RUNTIME_PALACE_ROOT")" = "$PALACE_LINK_BEFORE" ]; then
    pass "symlinks unchanged"
else
    fail "symlinks unchanged"
fi
if printf '%s' "$OUT_B" | grep -q "already correct"; then
    pass "second run reports already correct"
else
    fail "second run reports already correct"
fi

echo "== C: broken symlink -> repaired =="
rm -f "$RUNTIME_BRIDGE"
ln -s "$TMP/does-not-exist" "$RUNTIME_BRIDGE"
if run_runtime "" >/dev/null 2>&1; then pass "repair run exits 0"; else fail "repair run exits 0"; fi
if [ -L "$RUNTIME_BRIDGE" ] && [ "$(readlink "$RUNTIME_BRIDGE")" = "$CANONICAL_LINK" ]; then
    pass "broken symlink repaired"
else
    fail "broken symlink repaired"
fi

echo "== D: symlink to an old location -> re-pointed, old target intact =="
rm -f "$RUNTIME_BRIDGE"
mkdir -p "$(dirname "$RUNTIME_BRIDGE")"
ln -s "$OLD_TARGET" "$RUNTIME_BRIDGE"
OUT_D="$(run_runtime "" 2>&1)"
if [ -L "$RUNTIME_BRIDGE" ] && [ "$(readlink "$RUNTIME_BRIDGE")" = "$CANONICAL_LINK" ]; then
    pass "symlink re-pointed to the canonical link"
else
    fail "symlink re-pointed to the canonical link"
fi
if [ -d "$OLD_REPO" ] && [ -f "$OLD_REPO/pyproject.toml" ]; then
    pass "old target left untouched"
else
    fail "old target left untouched"
fi
if printf '%s' "$OUT_D" | grep -q "old target: $OLD_TARGET"; then
    pass "old target reported"
else
    fail "old target reported"
fi

echo "== E: real directory -> fatal, untouched =="
rm -f "$RUNTIME_BRIDGE"
mkdir -p "$RUNTIME_BRIDGE"
touch "$RUNTIME_BRIDGE/keep.txt"
if run_runtime "" >/dev/null 2>&1; then
    fail "real directory causes a fatal error"
else
    pass "real directory causes a fatal error"
fi
if [ -d "$RUNTIME_BRIDGE" ] && [ ! -L "$RUNTIME_BRIDGE" ] && [ -f "$RUNTIME_BRIDGE/keep.txt" ]; then
    pass "directory untouched"
else
    fail "directory untouched"
fi

echo "== F: regular file -> fatal, untouched =="
rm -rf "$RUNTIME_BRIDGE"
printf 'sentinel' > "$RUNTIME_BRIDGE"
if run_runtime "" >/dev/null 2>&1; then
    fail "regular file causes a fatal error"
else
    pass "regular file causes a fatal error"
fi
if [ -f "$RUNTIME_BRIDGE" ] && [ ! -L "$RUNTIME_BRIDGE" ] && [ "$(cat "$RUNTIME_BRIDGE")" = "sentinel" ]; then
    pass "file untouched"
else
    fail "file untouched"
fi

echo "== G: palace data is never deleted =="
rm -rf "$RUNTIME_BRIDGE" "$RUNTIME_PALACE_ROOT" "$TMP/opt"
mkdir -p "$PALACE_HOME/palace"
printf 'precious' > "$PALACE_HOME/palace/sentinel.txt"
run_runtime "" >/dev/null 2>&1
if [ -f "$PALACE_HOME/palace/sentinel.txt" ] && [ "$(cat "$PALACE_HOME/palace/sentinel.txt")" = "precious" ]; then
    pass "palace data preserved"
else
    fail "palace data preserved"
fi

echo "== H: unwritable parent without sudo -> explicit diagnostic =="
if [ "$(id -u)" -eq 0 ]; then
    echo "[SKIP] running as root — permission behaviour cannot be exercised"
else
    rm -rf "$TMP/opt" "$RUNTIME_BRIDGE"
    mkdir -p "$TMP/opt"
    chmod 555 "$TMP/opt"
    OUT_H="$(run_runtime "" 2>&1)"
    STATUS_H=$?
    chmod 755 "$TMP/opt"
    if [ "$STATUS_H" -ne 0 ]; then
        pass "unwritable parent causes a non-zero exit"
    else
        fail "unwritable parent causes a non-zero exit"
    fi
    if printf '%s' "$OUT_H" | grep -q "sudo ln -s --"; then
        pass "the manual fix command is printed"
    else
        fail "the manual fix command is printed"
    fi
    if [ ! -e "$RUNTIME_BRIDGE" ]; then
        pass "no partial alias was created"
    else
        fail "no partial alias was created"
    fi
fi

echo "== I: --status reports a wrong target =="
rm -rf "$RUNTIME_BRIDGE"
mkdir -p "$(dirname "$RUNTIME_BRIDGE")"
ln -s "$OLD_TARGET" "$RUNTIME_BRIDGE"
if run_runtime "--status" >/dev/null 2>&1; then
    fail "--status exits non-zero for a wrong target"
else
    pass "--status exits non-zero for a wrong target"
fi

echo "== J: correct aliases -> no-op even in interactive sudo mode =="
reset_aliases
ensure_canonical_link
run_policy "--no-sudo" >/dev/null 2>&1
reset_sudo_log
OUT_J="$(run_policy "--sudo=interactive" 2>&1)"
if [ $? -eq 0 ] && printf '%s' "$OUT_J" | grep -q "already correct"; then
    pass "a correct alias needs no privileges"
else
    fail "a correct alias needs no privileges"
fi
if sudo_was_called; then
    fail "a no-op must never invoke sudo"
else
    pass "a no-op never invokes sudo"
fi

if [ "$(id -u)" -eq 0 ]; then
    echo "[SKIP] running as root — permission behaviour cannot be exercised"
else
    echo "== K: --sudo=interactive without TTY -> hard error, no partial mutation =="
    reset_aliases
    ensure_canonical_link
    mkdir -p "$TMP/opt"
    chmod 555 "$TMP/opt"
    reset_sudo_log
    OUT_K="$(run_policy "--sudo=interactive" 2>&1)"
    STATUS_K=$?
    chmod 755 "$TMP/opt"
    if sudo_was_called; then
        fail "interactive mode without a TTY must not invoke sudo"
    else
        pass "interactive mode without a TTY does not invoke sudo"
    fi
    if [ "$STATUS_K" -ne 0 ]; then
        pass "interactive mode without a TTY fails"
    else
        fail "interactive mode without a TTY fails"
    fi
    if printf '%s' "$OUT_K" | grep -qi "TTY"; then
        pass "the diagnostic explains the missing TTY"
    else
        fail "the diagnostic explains the missing TTY"
    fi
    if [ ! -e "$RUNTIME_BRIDGE" ]; then
        pass "the privileged alias was not created"
    else
        fail "the privileged alias was not created"
    fi
    if [ ! -e "$RUNTIME_PALACE_ROOT" ]; then
        pass "the unprivileged alias was NOT created either (no partial mutation)"
    else
        fail "the unprivileged alias was NOT created either (no partial mutation)"
    fi

    echo "== M: real-directory conflict -> nothing is created elsewhere =="
    reset_aliases
    ensure_canonical_link
    mkdir -p "$RUNTIME_BRIDGE"
    touch "$RUNTIME_BRIDGE/keep.txt"
    if run_policy "--no-sudo" >/dev/null 2>&1; then
        fail "a real-directory conflict fails"
    else
        pass "a real-directory conflict fails"
    fi
    if [ -f "$RUNTIME_BRIDGE/keep.txt" ]; then
        pass "the conflicting directory is untouched"
    else
        fail "the conflicting directory is untouched"
    fi
    if [ ! -e "$RUNTIME_PALACE_ROOT" ]; then
        pass "no other alias was created (no partial mutation)"
    else
        fail "no other alias was created (no partial mutation)"
    fi
fi

echo "== L: --sudo=non-interactive succeeds when no privilege is needed =="
reset_aliases
ensure_canonical_link
if run_policy "--sudo=non-interactive" >/dev/null 2>&1; then
    pass "non-interactive mode works in a writable parent"
else
    fail "non-interactive mode works in a writable parent"
fi
if [ -L "$RUNTIME_BRIDGE" ] && [ -L "$RUNTIME_PALACE_ROOT" ]; then
    pass "both aliases exist after a non-interactive run"
else
    fail "both aliases exist after a non-interactive run"
fi

echo "== N: --print-manual and invalid sudo modes =="
OUT_N="$(run_policy "--print-manual" 2>&1)"
if [ $? -eq 0 ] && printf '%s' "$OUT_N" | grep -q "sudo ln -s"; then
    pass "--print-manual prints the manual commands"
else
    fail "--print-manual prints the manual commands"
fi
if run_policy "--sudo=bogus" >/dev/null 2>&1; then
    fail "an invalid sudo mode exits non-zero"
else
    pass "an invalid sudo mode exits non-zero"
fi

echo "== O: privileged path with (simulated) passwordless sudo =="
if [ "$(id -u)" -eq 0 ]; then
    echo "[SKIP] running as root — the privilege path is trivially satisfied"
else
    reset_aliases
    ensure_canonical_link
    mkdir -p "$TMP/opt"
    chmod 555 "$TMP/opt"
    reset_sudo_log
    OUT_O="$(run_policy "--sudo=non-interactive" 2>&1)"
    STATUS_O=$?
    chmod 755 "$TMP/opt"
    if [ "$STATUS_O" -eq 0 ]; then
        pass "a genuinely needed privilege is escalated for"
    else
        fail "a genuinely needed privilege is escalated for: $OUT_O"
    fi
    if [ -L "$RUNTIME_BRIDGE" ] && [ -L "$RUNTIME_PALACE_ROOT" ]; then
        pass "both aliases exist after the privileged run"
    else
        fail "both aliases exist after the privileged run"
    fi
    if sudo_was_called; then
        pass "sudo was used for the unwritable parent"
    else
        fail "sudo was used for the unwritable parent"
    fi
fi

echo "== P: fresh standard Linux host (/opt-like and /-like parents) =="
if [ "$(id -u)" -eq 0 ]; then
    echo "[SKIP] running as root — the privilege predicate is trivially satisfied"
else
    # (1) the plan must detect that a privilege is needed
    reset_aliases
    ensure_canonical_link
    fresh_host
    reset_sudo_log
    HOST_SUDO_MODE="diagnose"
    HOST_NOPASSWD="0"
    OUT_P="$(run_host_sim 2>&1)"
    STATUS_P=$?
    if [ "$STATUS_P" -ne 0 ]; then
        pass "diagnose refuses when the runtime roots need root"
    else
        fail "diagnose refuses when the runtime roots need root"
    fi
    if printf '%s' "$OUT_P" | grep -q "not writable"; then
        pass "the plan reports the missing privilege"
    else
        fail "the plan reports the missing privilege"
    fi
    if printf '%s' "$OUT_P" | grep -q "bash setup.sh"; then
        pass "diagnose points the operator at setup.sh"
    else
        fail "diagnose points the operator at setup.sh"
    fi
    if sudo_was_called; then
        fail "diagnose must not escalate at all"
    else
        pass "diagnose does not escalate"
    fi
    if [ ! -e "$HOST_BRIDGE" ] && [ ! -e "$HOST_PALACE" ]; then
        pass "no partial mutation when the privilege is unavailable"
    else
        fail "no partial mutation when the privilege is unavailable"
    fi

    # (2) interactive mode under a real PTY selects the sudo path
    if command -v script >/dev/null 2>&1; then
        fresh_host
        reset_sudo_log
        OUT_P2="$(run_host_sim_tty 2>&1)"
        STATUS_P2=$?
        if [ "$STATUS_P2" -eq 0 ]; then
            pass "a real TTY selects the interactive sudo path and succeeds"
        else
            fail "a real TTY selects the interactive sudo path and succeeds"
        fi
        if [ -L "$HOST_BRIDGE" ] && [ -L "$HOST_PALACE" ]; then
            pass "both aliases were created through the escalated path"
        else
            fail "both aliases were created through the escalated path"
        fi
        if grep -q '^ln ' "$SUDO_LOG" 2>/dev/null; then
            pass "the interactive path used bare sudo (never -n)"
        else
            fail "the interactive path used bare sudo (never -n)"
        fi
        if grep -q '^-n ' "$SUDO_LOG" 2>/dev/null; then
            fail "interactive mode must not probe with 'sudo -n'"
        else
            pass "interactive mode did not probe with 'sudo -n'"
        fi
    else
        echo "[SKIP] util-linux 'script' unavailable — cannot allocate a real PTY"
    fi

    # (3) a non-interactive mode must never attempt a prompt
    fresh_host
    reset_sudo_log
    HOST_SUDO_MODE="non-interactive"
    HOST_NOPASSWD="1"
    OUT_P3="$(run_host_sim 2>&1)"
    STATUS_P3=$?
    host_sim_unlocked
    if [ "$STATUS_P3" -ne 0 ]; then
        pass "non-interactive mode fails when passwordless sudo is unavailable"
    else
        fail "non-interactive mode fails when passwordless sudo is unavailable"
    fi
    if bare_sudo_was_called; then
        fail "non-interactive mode never invokes sudo without -n"
    else
        pass "non-interactive mode never invokes sudo without -n (no prompt possible)"
    fi
    if [ ! -e "$HOST_BRIDGE" ] && [ ! -e "$HOST_PALACE" ]; then
        pass "no partial mutation in non-interactive mode either"
    else
        fail "no partial mutation in non-interactive mode either"
    fi

    # (4) the palace home under $HOME stays writable regardless (sanity check)
    if [ -d "$FAKE_HOME/.mempalace" ]; then
        pass "the user-owned palace home is still created without privileges"
    else
        fail "the user-owned palace home is still created without privileges"
    fi
fi

echo ""
echo "─────────────────────────────────────────"
echo " $PASS passed, $FAIL failed."
echo "─────────────────────────────────────────"

[ "$FAIL" -eq 0 ]
