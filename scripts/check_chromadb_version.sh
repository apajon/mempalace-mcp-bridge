#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[ERROR] Virtual environment not found — run: bash setup.sh" >&2
    exit 1
fi

exec "$VENV_PYTHON" "$REPO_ROOT/scripts/check_chromadb_version.py"
