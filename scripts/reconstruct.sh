#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROTOTYPE_SCRIPT="$REPO_ROOT/scripts/palace_reconstruction_prototype.py"
DEFAULT_SOURCE_PYTHON="$REPO_ROOT/.venv/bin/python"
DEFAULT_TARGET_PYTHON="$REPO_ROOT/.venv/bin/python"
DEFAULT_MCP_LAUNCHER="$REPO_ROOT/scripts/run_mcp_server_exploration.py"

SOURCE_PALACE=""
TARGET_PALACE=""
WORK_DIR=""
SOURCE_PYTHON="$DEFAULT_SOURCE_PYTHON"
TARGET_PYTHON="$DEFAULT_TARGET_PYTHON"
MCP_LAUNCHER="$DEFAULT_MCP_LAUNCHER"
WITH_USAGE=false
WITH_MCP_RUNTIME=false
DRY_RUN=false
DEBUG=false

STEP_INDEX=0
TOTAL_STEPS=6
CURRENT_STEP=""

usage() {
    cat <<'EOF'
Usage:
  ./scripts/reconstruct.sh \
    --source-palace PATH \
    --target-palace PATH \
    --work-dir PATH \
    [--source-python PATH] \
    [--target-python PATH] \
    [--with-usage] \
    [--with-mcp-runtime] \
    [--mcp-launcher-script PATH] \
    [--dry-run]

Required:
  --source-palace PATH       Source palace to export from (expected chroma_0_6).
  --target-palace PATH       Fresh target palace directory to import into.
  --work-dir PATH            Run directory for the export bundle and validation artifacts.

Optional:
  --source-python PATH       Python executable for source-side export and source retrieval checks.
                             Default: ./.venv/bin/python from this repo.
  --target-python PATH       Python executable for target-side import and validation checks.
                             Default: ./.venv/bin/python from this repo.
  --with-usage               Also run usage recording and comparison.
  --with-mcp-runtime         Also run experimental MCP runtime validation against the target.
  --mcp-launcher-script PATH Launcher script used with --with-mcp-runtime.
                             Default: scripts/run_mcp_server_exploration.py
  --dry-run                  Print the pipeline without executing it.
  --debug                    Pass --debug to the reconstruction script for full tracebacks.
  --help                     Show this help text.

Notes:
  - This workflow remains experimental and source-preserving.
  - The work dir must be empty or absent before the run.
  - The target palace must be empty or absent before the run.
EOF
}

info() {
    echo "[INFO]  $*"
}

ok() {
    echo "[OK]    $*"
}

fail() {
    echo "[ERROR] $*" >&2
    exit 1
}

resolve_path() {
    python3 -c 'import os, sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$1"
}

quote_command() {
    local arg
    for arg in "$@"; do
        printf '%q ' "$arg"
    done
}

on_error() {
    local exit_code="$1"
    if [ -n "$CURRENT_STEP" ]; then
        echo "[ERROR] Step $STEP_INDEX/$TOTAL_STEPS failed: $CURRENT_STEP" >&2
        if [ -n "$WORK_DIR" ] && [ "$DRY_RUN" = false ]; then
            echo "[INFO]  Work dir for reconstruction artifacts: $WORK_DIR" >&2
        fi
    fi
    exit "$exit_code"
}

trap 'on_error "$?"' ERR

while [ "$#" -gt 0 ]; do
    case "$1" in
        --source-palace)
            [ "$#" -ge 2 ] || fail "Missing value for --source-palace"
            SOURCE_PALACE="$2"
            shift 2
            ;;
        --target-palace)
            [ "$#" -ge 2 ] || fail "Missing value for --target-palace"
            TARGET_PALACE="$2"
            shift 2
            ;;
        --work-dir)
            [ "$#" -ge 2 ] || fail "Missing value for --work-dir"
            WORK_DIR="$2"
            shift 2
            ;;
        --source-python)
            [ "$#" -ge 2 ] || fail "Missing value for --source-python"
            SOURCE_PYTHON="$2"
            shift 2
            ;;
        --target-python)
            [ "$#" -ge 2 ] || fail "Missing value for --target-python"
            TARGET_PYTHON="$2"
            shift 2
            ;;
        --mcp-launcher-script)
            [ "$#" -ge 2 ] || fail "Missing value for --mcp-launcher-script"
            MCP_LAUNCHER="$2"
            shift 2
            ;;
        --with-usage)
            WITH_USAGE=true
            shift
            ;;
        --with-mcp-runtime)
            WITH_MCP_RUNTIME=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --debug)
            DEBUG=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            fail "Unknown option: $1"
            ;;
    esac
done

[ -n "$SOURCE_PALACE" ] || fail "Missing required --source-palace"
[ -n "$TARGET_PALACE" ] || fail "Missing required --target-palace"
[ -n "$WORK_DIR" ] || fail "Missing required --work-dir"

SOURCE_PALACE="$(resolve_path "$SOURCE_PALACE")"
TARGET_PALACE="$(resolve_path "$TARGET_PALACE")"
WORK_DIR="$(resolve_path "$WORK_DIR")"
SOURCE_PYTHON="$(resolve_path "$SOURCE_PYTHON")"
TARGET_PYTHON="$(resolve_path "$TARGET_PYTHON")"
MCP_LAUNCHER="$(resolve_path "$MCP_LAUNCHER")"

EXPORT_DIR="$WORK_DIR/export-bundle"
SOURCE_RETRIEVAL_RESULTS="$WORK_DIR/source-retrieval-results.json"
TARGET_RETRIEVAL_RESULTS="$WORK_DIR/target-retrieval-results.json"
SOURCE_USAGE_RESULTS="$WORK_DIR/source-usage-results.json"
TARGET_USAGE_RESULTS="$WORK_DIR/target-usage-results.json"

if [ "$WITH_USAGE" = true ]; then
    TOTAL_STEPS=$((TOTAL_STEPS + 3))
fi
if [ "$WITH_MCP_RUNTIME" = true ]; then
    TOTAL_STEPS=$((TOTAL_STEPS + 1))
fi

[ -f "$PROTOTYPE_SCRIPT" ] || fail "Prototype script not found: $PROTOTYPE_SCRIPT"
[ -x "$SOURCE_PYTHON" ] || fail "Source Python is not executable: $SOURCE_PYTHON"
[ -x "$TARGET_PYTHON" ] || fail "Target Python is not executable: $TARGET_PYTHON"
[ -d "$SOURCE_PALACE" ] || fail "Source palace not found: $SOURCE_PALACE"

if [ "$WITH_MCP_RUNTIME" = true ]; then
    [ -f "$MCP_LAUNCHER" ] || fail "MCP launcher script not found: $MCP_LAUNCHER"
fi

if [ -e "$WORK_DIR" ] && [ ! -d "$WORK_DIR" ]; then
    fail "Work dir exists but is not a directory: $WORK_DIR"
fi

if [ -e "$WORK_DIR" ] && [ -n "$(find "$WORK_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    fail "Work dir must be empty or absent: $WORK_DIR"
fi

if [ -e "$EXPORT_DIR" ]; then
    fail "Export bundle path already exists: $EXPORT_DIR"
fi

if [ -e "$TARGET_PALACE" ] && [ ! -d "$TARGET_PALACE" ]; then
    fail "Target palace exists but is not a directory: $TARGET_PALACE"
fi

if [ -e "$TARGET_PALACE" ] && [ -n "$(find "$TARGET_PALACE" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    fail "Target palace must be empty or absent: $TARGET_PALACE"
fi

mkdir -p "$(dirname "$WORK_DIR")"

run_step() {
    local step_label="$1"
    shift

    STEP_INDEX=$((STEP_INDEX + 1))
    CURRENT_STEP="$step_label"

    # Inject --debug before the subcommand arguments when DEBUG is enabled.
    local cmd=("$@")
    if [ "$DEBUG" = true ]; then
        # Insert --debug after the script path (position 2) and before subcommand args.
        cmd=("${cmd[0]}" "${cmd[1]}" "--debug" "${cmd[@]:2}")
    fi

    info "Step $STEP_INDEX/$TOTAL_STEPS — $step_label"
    info "Command: $(quote_command "${cmd[@]}")"

    if [ "$DRY_RUN" = true ]; then
        echo ""
        return 0
    fi

    "${cmd[@]}"
    ok "Completed step $STEP_INDEX/$TOTAL_STEPS"
    echo ""
}

echo "════════════════════════════════════════"
echo " MemPalace Reconstruction Pipeline"
echo "════════════════════════════════════════"
echo ""
info "Source palace: $SOURCE_PALACE"
info "Target palace: $TARGET_PALACE"
info "Work dir: $WORK_DIR"
info "Source Python: $SOURCE_PYTHON"
info "Target Python: $TARGET_PYTHON"
info "Usage validation: $WITH_USAGE"
info "MCP runtime validation: $WITH_MCP_RUNTIME"
if [ "$DEBUG" = true ]; then
    info "Debug mode: true"
fi
if [ "$DRY_RUN" = true ]; then
    info "Dry run: true"
fi
echo ""

if [ "$DRY_RUN" = false ]; then
    mkdir -p "$WORK_DIR"
fi

run_step \
    "Export source palace to a neutral bundle (0.6.x runtime)" \
    "$SOURCE_PYTHON" "$PROTOTYPE_SCRIPT" export \
    --source-palace "$SOURCE_PALACE" \
    --output-dir "$EXPORT_DIR"

run_step \
    "Import bundle into the target palace (target runtime)" \
    "$TARGET_PYTHON" "$PROTOTYPE_SCRIPT" import \
    --export-dir "$EXPORT_DIR" \
    --target-palace "$TARGET_PALACE"

run_step \
    "Validate structural reconstruction" \
    "$TARGET_PYTHON" "$PROTOTYPE_SCRIPT" validate \
    --export-dir "$EXPORT_DIR" \
    --target-palace "$TARGET_PALACE"

run_step \
    "Record retrieval behavior on the source palace" \
    "$SOURCE_PYTHON" "$PROTOTYPE_SCRIPT" record-retrieval \
    --palace "$SOURCE_PALACE" \
    --queries-file "$EXPORT_DIR/reconstruction-retrieval-queries.json" \
    --output "$SOURCE_RETRIEVAL_RESULTS" \
    --label source

run_step \
    "Record retrieval behavior on the target palace" \
    "$TARGET_PYTHON" "$PROTOTYPE_SCRIPT" record-retrieval \
    --palace "$TARGET_PALACE" \
    --queries-file "$EXPORT_DIR/reconstruction-retrieval-queries.json" \
    --output "$TARGET_RETRIEVAL_RESULTS" \
    --label target

run_step \
    "Compare retrieval results" \
    "$TARGET_PYTHON" "$PROTOTYPE_SCRIPT" compare-retrieval \
    --source-results "$SOURCE_RETRIEVAL_RESULTS" \
    --target-results "$TARGET_RETRIEVAL_RESULTS"

if [ "$WITH_USAGE" = true ]; then
    run_step \
        "Record usage behavior on the source palace" \
        "$SOURCE_PYTHON" "$PROTOTYPE_SCRIPT" record-usage \
        --palace "$SOURCE_PALACE" \
        --scenarios-file "$EXPORT_DIR/reconstruction-usage-scenarios.json" \
        --output "$SOURCE_USAGE_RESULTS" \
        --label source

    run_step \
        "Record usage behavior on the target palace" \
        "$TARGET_PYTHON" "$PROTOTYPE_SCRIPT" record-usage \
        --palace "$TARGET_PALACE" \
        --scenarios-file "$EXPORT_DIR/reconstruction-usage-scenarios.json" \
        --output "$TARGET_USAGE_RESULTS" \
        --label target

    run_step \
        "Compare usage results" \
        "$TARGET_PYTHON" "$PROTOTYPE_SCRIPT" compare-usage \
        --source-results "$SOURCE_USAGE_RESULTS" \
        --target-results "$TARGET_USAGE_RESULTS"
fi

if [ "$WITH_MCP_RUNTIME" = true ]; then
    run_step \
        "Validate MCP runtime against the target palace" \
        "$TARGET_PYTHON" "$PROTOTYPE_SCRIPT" validate-mcp-runtime \
        --export-dir "$EXPORT_DIR" \
        --palace "$TARGET_PALACE" \
        --python "$TARGET_PYTHON" \
        --launcher-script "$MCP_LAUNCHER"
fi

CURRENT_STEP=""

echo "════════════════════════════════════════"
echo " Reconstruction pipeline complete"
echo "════════════════════════════════════════"
echo ""
ok "Bundle written to $EXPORT_DIR"
ok "Target palace ready at $TARGET_PALACE"
ok "Retrieval artifacts written to $SOURCE_RETRIEVAL_RESULTS and $TARGET_RETRIEVAL_RESULTS"
if [ "$WITH_USAGE" = true ]; then
    ok "Usage artifacts written to $SOURCE_USAGE_RESULTS and $TARGET_USAGE_RESULTS"
fi
