#!/usr/bin/env bash
# scripts/runtime_aliases.sh
#
# Owns the two *runtime* path aliases that let a single, user-agnostic
# `.mcp.json` work unchanged both on the host and inside a DevContainer:
#
#     /opt/mempalace-mcp-bridge   ->   $HOME/.local/share/mempalace-mcp-bridge
#                                      (which itself -> the real clone)
#     /mempalace                  ->   $HOME/.mempalace
#
# Rationale: the real clone may live anywhere and the palace is host-owned under
# $HOME/.mempalace, but MCP config / devcontainer mounts / scripts must reference
# fixed, location-independent paths. `link_bridge.sh` owns the canonical
# per-user link; this script owns the *universal runtime* aliases on top of it.
#
# Safe and idempotent behaviour (per alias):
#   - alias absent                      -> create the symlink
#   - symlink already correct           -> success, no destructive action
#   - broken symlink                    -> re-point to the expected target
#   - symlink to an old/other location  -> report old target, re-point
#                                          (the previous target is NEVER deleted)
#   - real directory or regular file    -> explicit error, object left untouched
#   - parent not writable               -> sudo according to SUDO_MODE (below),
#                                          otherwise a clear manual-fix diagnostic
#
# Privilege model (SUDO_MODE):
#   auto (default)    interactive sudo when stdin is a TTY, otherwise sudo -n
#   interactive       sudo may prompt for a password (requires a TTY)
#   non-interactive   sudo -n only — never prompts, can never hang
#   diagnose          never escalate; a required privilege is reported with
#                     instructions (`never` and `--no-sudo` are aliases)
#
#   On a fresh, standard Linux host, creating these two aliases genuinely needs
#   root: /opt and / are not writable by a normal user. That is expected, not a
#   bug.
#
#     setup.sh     -> `auto`      an interactive install MAY prompt for a sudo
#                                 password (an already-correct alias is a no-op
#                                 and prompts for nothing)
#     update.sh    -> `diagnose`  a routine update never escalates and never
#                                 waits for a prompt; if root is required it
#                                 stops and points the operator at setup.sh
#     tests / CI   -> jailed sudo / `diagnose`
#
#   The script always plans both aliases first, verifies that every planned
#   mutation is achievable, and only then mutates — so a missing privilege never
#   leaves a half-applied state.
#
# Testing / override seams (not part of the user-facing contract):
#   MEMPALACE_RUNTIME_BRIDGE_PATH  (default /opt/mempalace-mcp-bridge)
#   MEMPALACE_RUNTIME_PALACE_ROOT  (default /mempalace)
#   MEMPALACE_RUNTIME_SUDO         (default auto; same values as --sudo=)
#   MEMPALACE_RUNTIME_ALLOW_SUDO   (default 1; set 0 = --sudo=diagnose)
#
# Usage:
#   bash scripts/runtime_aliases.sh                  # ensure both aliases
#   bash scripts/runtime_aliases.sh --status         # report state, non-fatal exit
#   bash scripts/runtime_aliases.sh --non-interactive
#   bash scripts/runtime_aliases.sh --sudo=diagnose  # never escalate
#   bash scripts/runtime_aliases.sh --no-sudo        # alias of --sudo=diagnose
#   bash scripts/runtime_aliases.sh --sudo=interactive
#   bash scripts/runtime_aliases.sh --print-manual   # show manual commands
#
# Exit codes:
#   0 — both aliases are correct
#   1 — at least one alias could not be ensured (diagnostics on stderr)
#   2 — usage error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"

: "${HOME:?HOME must be set to locate the canonical bridge link and palace}"

CANONICAL_LINK="${HOME}/.local/share/mempalace-mcp-bridge"
PALACE_HOME="${HOME}/.mempalace"

BRIDGE_RUNTIME_LINK="${MEMPALACE_RUNTIME_BRIDGE_PATH:-/opt/mempalace-mcp-bridge}"
PALACE_RUNTIME_ROOT="${MEMPALACE_RUNTIME_PALACE_ROOT:-/mempalace}"

# SUDO_MODE is declared here (before the helpers that read it) and refined by the
# command-line parser below.
SUDO_MODE="${MEMPALACE_RUNTIME_SUDO:-auto}"
if [ "${MEMPALACE_RUNTIME_ALLOW_SUDO:-1}" = "0" ]; then
    SUDO_MODE="diagnose"
fi

info() { echo "[INFO]  $*"; }
ok()   { echo "[OK]    $*"; }
warn() { echo "[WARN]  $*" >&2; }

FAILED=0

alias_error() {
    local line
    for line in "$@"; do
        echo "[ERROR] $line" >&2
    done
    FAILED=1
}

# ─── Path helpers ─────────────────────────────────────────────────────────────

# Best-effort physical resolution (follows symlinks in all path components).
physical() {
    readlink -f -- "$1" 2>/dev/null || true
}

# True when a symlink at $1 either points at the literal target $2 or resolves to
# the physical path $3. Accepting both covers a correct-but-currently-dangling
# alias (e.g. created before the palace directory exists).
alias_points_to() {
    local link="$1" desired="$2" desired_phys="$3"
    local raw resolved
    raw="$(readlink -- "$link" 2>/dev/null || true)"
    resolved="$(physical "$link")"

    [ "$raw" = "$desired" ] && return 0
    [ -n "$desired_phys" ] && [ -n "$resolved" ] && [ "$resolved" = "$desired_phys" ] && return 0
    return 1
}

# ─── Privilege model ──────────────────────────────────────────────────────────
#
# /opt and / are root-owned on a standard Linux host, so creating or replacing
# the runtime aliases usually needs root. Policy:
#
#   auto (default)    interactive sudo when stdin is a TTY, otherwise sudo -n
#   interactive       sudo may prompt (requires a TTY, otherwise a hard error)
#   non-interactive   sudo -n only — can never prompt, can never hang
#   never             no sudo at all (offline / unprivileged environments)
#
# An alias that is already correct is a no-op and never looks for privileges.
# setup.sh uses the default (a human is present); update.sh and CI pass
# `--non-interactive` so a missing sudo can never block them.
#
# SUDO_MODE was resolved from the environment above and may be refined by the
# command-line parser at the bottom of this file.

sudo_present() {
    command -v sudo >/dev/null 2>&1
}

stdin_is_tty() {
    [ -t 0 ]
}

# Echo the command to prefix (empty when unprivileged access is enough).
# Returns non-zero when the requested mode cannot be satisfied right now.
resolve_sudo_verb() {
    case "$SUDO_MODE" in
        diagnose)
            return 1
            ;;
        interactive)
            sudo_present || return 1
            stdin_is_tty || return 1
            echo "sudo"
            ;;
        non-interactive)
            sudo_present || return 1
            sudo -n true >/dev/null 2>&1 || return 1
            echo "sudo -n"
            ;;
        auto)
            sudo_present || return 1
            if stdin_is_tty; then
                echo "sudo"
            else
                sudo -n true >/dev/null 2>&1 || return 1
                echo "sudo -n"
            fi
            ;;
        *)
            return 1
            ;;
    esac
}

sudo_mode_explanation() {
    case "$SUDO_MODE" in
        diagnose) echo "sudo was deliberately not used (mode 'diagnose': this caller must not escalate)" ;;
        interactive) echo "sudo mode 'interactive' was requested but no TTY is attached to stdin" ;;
        non-interactive) echo "sudo mode 'non-interactive' was requested but 'sudo -n' is unavailable" ;;
        *) echo "sudo is unavailable on this host" ;;
    esac
}

# Remediation block printed when an alias cannot be created without privileges.
print_remediation() {
    local link="$1" target="$2"
    if [ "$SUDO_MODE" = "diagnose" ]; then
        echo "[ERROR] Re-run the interactive installer; it may prompt for your sudo password:" >&2
        echo "[ERROR]   bash setup.sh" >&2
        echo "[ERROR] Or create this alias manually:" >&2
        echo "[ERROR]   sudo ln -s -- '$target' '$link'" >&2
    else
        echo "[ERROR] Run this manually, then re-run setup:" >&2
        echo "[ERROR]   sudo ln -s -- '$target' '$link'" >&2
    fi
}

privilege_error() {
    local label="$1" link="$2" target="$3" verb="$4"
    alias_error \
        "Cannot $verb the $label runtime alias '$link': its parent directory is not writable." \
        "$(sudo_mode_explanation)"
    print_remediation "$link" "$target"
}

# ─── Alias mutation ───────────────────────────────────────────────────────────

# True when a symlink at $1 can be created or replaced **without privileges**:
# either the parent already exists and is writable, or its nearest existing
# ancestor is writable (so `mkdir -p` will succeed). Getting this wrong is what
# makes a script ask for a password it does not need.
path_creatable_without_privileges() {
    local parent
    parent="$(dirname -- "$1")"
    while [ ! -d "$parent" ]; do
        local next
        next="$(dirname -- "$parent")"
        [ "$next" = "$parent" ] && break
        parent="$next"
    done
    [ -d "$parent" ] && [ -w "$parent" ]
}

# `$4` is a deliberately unquoted command prefix ("sudo", "sudo -n" or empty).
# shellcheck disable=SC2086
apply_create() {
    local link="$1" target="$2" label="$3" sudo_verb="${4:-}"
    local parent
    parent="$(dirname -- "$link")"

    if [ -z "$sudo_verb" ]; then
        [ -d "$parent" ] || mkdir -p -- "$parent" 2>/dev/null || return 1
        ln -s -- "$target" "$link" 2>/dev/null
        return $?
    fi

    $sudo_verb mkdir -p -- "$parent" 2>/dev/null || return 1
    $sudo_verb ln -s -- "$target" "$link" 2>/dev/null
}

# shellcheck disable=SC2086
apply_replace() {
    local link="$1" target="$2" label="$3" sudo_verb="${4:-}"

    if [ -z "$sudo_verb" ]; then
        rm -f -- "$link" 2>/dev/null && ln -s -- "$target" "$link" 2>/dev/null
        return $?
    fi

    $sudo_verb rm -f -- "$link" 2>/dev/null || return 1
    $sudo_verb ln -s -- "$target" "$link" 2>/dev/null
}

# ─── Core ensure / status ─────────────────────────────────────────────────────

# ─── Plan / apply ─────────────────────────────────────────────────────────────
#
# Two phases: first *plan* every alias (strictly read-only), then verify that
# every planned mutation is achievable, and only then mutate. This is what makes
# "no partial mutation" true even when the second alias needs privileges the
# first one does not.

PLAN_ACTIONS=()
PLAN_LINKS=()
PLAN_TARGETS=()
PLAN_LABELS=()

# plan_alias <link> <desired-target> <desired-physical> <label>
plan_alias() {
    local link="$1" desired="$2" desired_phys="$3" label="$4"

    # Absent (neither a filesystem object nor a symlink) -> create.
    if [ ! -e "$link" ] && [ ! -L "$link" ]; then
        info "$label runtime alias absent — would create $link -> $desired"
        PLAN_ACTIONS+=("create")
        PLAN_LINKS+=("$link")
        PLAN_TARGETS+=("$desired")
        PLAN_LABELS+=("$label")
        return 0
    fi

    if [ -L "$link" ]; then
        if alias_points_to "$link" "$desired" "$desired_phys"; then
            PLAN_ACTIONS+=("noop")
            PLAN_LINKS+=("$link")
            PLAN_TARGETS+=("$desired")
            PLAN_LABELS+=("$label")
            return 0
        fi

        local old_target
        old_target="$(readlink -- "$link" 2>/dev/null || true)"
        if [ -e "$link" ]; then
            warn "$label runtime alias points to another location:"
            warn "  old target: ${old_target:-<unreadable>}"
        else
            warn "$label runtime alias is broken (missing target):"
            warn "  stale target: ${old_target:-<unreadable>}"
        fi

        PLAN_ACTIONS+=("replace")
        PLAN_LINKS+=("$link")
        PLAN_TARGETS+=("$desired")
        PLAN_LABELS+=("$label")
        return 0
    fi

    # Exists but is NOT a symlink: a real directory or regular file.
    if [ -d "$link" ]; then
        alias_error \
            "$label runtime alias path '$link' is a real directory." \
            "Refusing to modify it. Remove or rename it manually, then re-run setup."
    else
        alias_error \
            "$label runtime alias path '$link' is a regular file." \
            "Refusing to modify it. Remove or rename it manually, then re-run setup."
    fi
    return 1
}

ensure_all() {
    ensure_palace_home || true

    PLAN_ACTIONS=()
    PLAN_LINKS=()
    PLAN_TARGETS=()
    PLAN_LABELS=()

    plan_alias "$BRIDGE_RUNTIME_LINK" "$CANONICAL_LINK" "$(physical "$REPO_ROOT")" "Bridge" || true
    plan_alias "$PALACE_RUNTIME_ROOT" "$PALACE_HOME" "$(physical "$PALACE_HOME")" "Palace" || true

    # Phase 1 failure: a planned target is a real filesystem object. Nothing has
    # been touched yet, and nothing will be.
    if [ "$FAILED" -ne 0 ]; then
        echo "" >&2
        echo "[ERROR] Refusing to change anything: a runtime alias path is a real filesystem object." >&2
        exit 1
    fi

    # Phase 2: verify that every planned mutation is achievable before mutating.
    local needs_privilege=0 index
    for index in "${!PLAN_ACTIONS[@]}"; do
        case "${PLAN_ACTIONS[$index]}" in
            create|replace)
                path_creatable_without_privileges "${PLAN_LINKS[$index]}" || needs_privilege=1
                ;;
        esac
    done

    local privilege_verb=""
    if [ "$needs_privilege" -eq 1 ]; then
        if ! privilege_verb="$(resolve_sudo_verb)"; then
            privilege_verb=""
            for index in "${!PLAN_ACTIONS[@]}"; do
                case "${PLAN_ACTIONS[$index]}" in
                    create|replace)
                        if ! path_creatable_without_privileges "${PLAN_LINKS[$index]}"; then
                            privilege_error \
                                "${PLAN_LABELS[$index]}" \
                                "${PLAN_LINKS[$index]}" \
                                "${PLAN_TARGETS[$index]}" \
                                "${PLAN_ACTIONS[$index]}"
                        fi
                        ;;
                esac
            done
            echo "" >&2
            echo "[ERROR] Refusing to change anything: the required privileges are unavailable." >&2
            echo "[ERROR] The universal .mcp.json needs $BRIDGE_RUNTIME_LINK and $PALACE_RUNTIME_ROOT." >&2
            exit 1
        fi
    fi

    # Phase 3: apply.
    local action link target label verb
    for index in "${!PLAN_ACTIONS[@]}"; do
        action="${PLAN_ACTIONS[$index]}"
        link="${PLAN_LINKS[$index]}"
        target="${PLAN_TARGETS[$index]}"
        label="${PLAN_LABELS[$index]}"
        case "$action" in
            noop)
                ok "$label runtime alias already correct: $link -> $target"
                ;;
            create)
                verb=""
                path_creatable_without_privileges "$link" || verb="$privilege_verb"
                if apply_create "$link" "$target" "$label" "$verb"; then
                    ok "Created $label runtime alias: $link -> $target"
                else
                    alias_error "Failed to create the $label runtime alias '$link'."
                fi
                ;;
            replace)
                verb=""
                path_creatable_without_privileges "$link" || verb="$privilege_verb"
                if apply_replace "$link" "$target" "$label" "$verb"; then
                    ok "Updated $label runtime alias: $link -> $target"
                else
                    alias_error "Failed to update the $label runtime alias '$link'."
                fi
                ;;
        esac
    done

    if [ "$FAILED" -ne 0 ]; then
        echo "" >&2
        echo "[ERROR] Runtime aliases are incomplete — the universal .mcp.json would not work." >&2
        print_remediation "$BRIDGE_RUNTIME_LINK" "$CANONICAL_LINK"
        print_remediation "$PALACE_RUNTIME_ROOT" "$PALACE_HOME"
        exit 1
    fi

    ok "Runtime aliases verified ($BRIDGE_RUNTIME_LINK, $PALACE_RUNTIME_ROOT)"
    return 0
}

status_alias() {
    local link="$1" desired="$2" desired_phys="$3" label="$4"

    if [ ! -e "$link" ] && [ ! -L "$link" ]; then
        info "$label runtime alias: ABSENT ($link)"
        return 1
    fi

    if [ -L "$link" ]; then
        local raw resolved
        raw="$(readlink -- "$link" 2>/dev/null || true)"
        resolved="$(physical "$link")"
        info "$label runtime alias: $link"
        info "  target (raw):      ${raw:-<unreadable>}"
        info "  target (resolved): ${resolved:-<broken>}"
        if alias_points_to "$link" "$desired" "$desired_phys"; then
            ok "  correct (expected $desired)"
            return 0
        fi
        warn "  INCORRECT (expected $desired)"
        return 1
    fi

    warn "$label runtime alias path is a real filesystem object (not a symlink): $link"
    return 1
}

ensure_palace_home() {
    # The palace home is user-owned; creating it is safe and matches the
    # documented contract ("the installer may ensure expected directories
    # exist"). It is never deleted or relocated.
    if [ ! -d "$PALACE_HOME" ]; then
        info "Creating palace home directory: $PALACE_HOME"
        if ! mkdir -p -- "$PALACE_HOME" 2>/dev/null; then
            alias_error \
                "Could not create palace home directory '$PALACE_HOME'." \
                "Its parent is not writable. Create it manually, then re-run setup."
            return 1
        fi
    fi
    return 0
}

print_manual() {
    echo "Manual runtime alias commands (these need root on a standard Linux host):"
    echo "  sudo ln -s -- '$CANONICAL_LINK' '$BRIDGE_RUNTIME_LINK'"
    echo "  sudo ln -s -- '$PALACE_HOME' '$PALACE_RUNTIME_ROOT'"
    echo ""
    echo "Or run the interactive installer, which may prompt for your sudo password:"
    echo "  bash setup.sh"
}

# ─── Main ─────────────────────────────────────────────────────────────────────

MODE="ensure"
for arg in "$@"; do
    case "$arg" in
        --no-sudo) SUDO_MODE="diagnose" ;;
        --non-interactive) SUDO_MODE="non-interactive" ;;
        --interactive) SUDO_MODE="interactive" ;;
        --sudo=*) SUDO_MODE="${arg#--sudo=}" ;;
        --status) MODE="status" ;;
        --print-manual) MODE="manual" ;;
        ""|--ensure) MODE="ensure" ;;
        *)
            echo "Usage: $0 [--ensure|--status|--print-manual] [--no-sudo|--non-interactive|--interactive|--sudo=MODE]" >&2
            exit 2
            ;;
    esac
done

# Normalise and validate the sudo policy.
case "$SUDO_MODE" in
    auto|interactive|non-interactive|diagnose) ;;
    never) SUDO_MODE="diagnose" ;;
    *)
        echo "Usage: invalid sudo mode '$SUDO_MODE' (auto|interactive|non-interactive|diagnose)" >&2
        exit 2
        ;;
esac

case "$MODE" in
    manual)
        print_manual
        exit 0
        ;;
    status)
        STATUS_FAILED=0
        status_alias "$BRIDGE_RUNTIME_LINK" "$CANONICAL_LINK" "$(physical "$REPO_ROOT")" "Bridge" || STATUS_FAILED=1
        status_alias "$PALACE_RUNTIME_ROOT" "$PALACE_HOME" "$(physical "$PALACE_HOME")" "Palace" || STATUS_FAILED=1
        exit "$STATUS_FAILED"
        ;;
    ensure)
        ensure_all
        exit 0
        ;;
esac
