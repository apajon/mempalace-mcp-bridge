#!/usr/bin/env bash
# scripts/bootstrap.sh
# Installs uv (if missing) and MemPalace into a local virtual environment.
# Safe to run multiple times (idempotent).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

info()  { echo "[INFO]  $*"; }
ok()    { echo "[OK]    $*"; }
fail()  { echo "[ERROR] $*" >&2; exit 1; }

# ─── Check / install uv ───────────────────────────────────────────────────────

if command -v uv &>/dev/null; then
    ok "uv found: $(command -v uv) ($(uv --version))"
else
    info "uv not found — installing via official installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Reload PATH for the rest of this script
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        fail "uv installation failed or not in PATH. Add uv to PATH and re-run."
    fi
    ok "uv installed: $(uv --version)"
fi

# ─── Create virtual environment ───────────────────────────────────────────────

VENV_DIR="$REPO_ROOT/.venv"

if [ -d "$VENV_DIR" ]; then
    info "Virtual environment already exists at $VENV_DIR"
else
    info "Creating virtual environment at $VENV_DIR ..."
    uv venv "$VENV_DIR" --python 3.12
    ok "Virtual environment created"
fi

# ─── Install MemPalace ────────────────────────────────────────────────────────

info "Installing MemPalace..."
uv pip install --python "$VENV_DIR/bin/python" "mempalace>=3.0.0" "chromadb>=0.6,<0.7"
bash "$REPO_ROOT/scripts/check_chromadb_version.sh"

# Verify
if uv run --python "$VENV_DIR/bin/python" mempalace --version &>/dev/null 2>&1 || \
   "$VENV_DIR/bin/python" -m mempalace --version &>/dev/null 2>&1 || \
   "$VENV_DIR/bin/mempalace" --version &>/dev/null 2>&1; then
    ok "MemPalace installed successfully"
else
    # Installation may still be fine even if --version flag doesn't exist
    info "MemPalace package installed (version flag may not be available — run verify_install.sh to confirm)"
fi

echo ""
echo "Bootstrap complete."
echo ""
echo "Next steps:"
echo "  bash scripts/init_palace.sh       # Initialize MemPalace"
echo "  bash scripts/mine_sample_data.sh  # Mine example notes"
echo "  bash scripts/verify_install.sh    # Verify everything works"
