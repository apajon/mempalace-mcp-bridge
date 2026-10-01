# Installation Guide

This guide covers the full installation process for MemPalace using `uv`.

---

## 1. Install uv

`uv` is a fast Python package and project manager. It replaces `pip`, `venv`, and `pyenv` for most workflows.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation, reload your shell:

```bash
source ~/.bashrc   # or ~/.zshrc, ~/.profile depending on your shell
```

Verify:

```bash
uv --version
# uv 0.x.y (...)
```

> **Note:** `uv` installs to `~/.cargo/bin/` or `~/.local/bin/` depending on your system. Make sure that directory is in your `PATH`.

---

## 2. Set the Python version

This repository includes a `.python-version` file pinned to `3.12`. `uv` will use this automatically when creating the virtual environment.

Verify `uv` can find Python 3.12:

```bash
uv python list
```

If Python 3.12 is not listed, install it:

```bash
uv python install 3.12
```

---

## 3. Create the virtual environment

```bash
uv venv .venv --python 3.12
```

This creates a `.venv/` directory in the current folder. It is excluded from version control via `.gitignore`.

---

## 4. Install MemPalace

```bash
uv pip install --python .venv/bin/python "mempalace>=3.0.0" "chromadb>=0.6,<0.7"
```

This installs MemPalace and keeps ChromaDB on the tested `0.6.x` line, which avoids
the `chromadb` 1.x database incompatibility with older palaces.

The stable `main` branch assumes that contract explicitly and fails fast if the installed
`chromadb` version is outside `0.6.x`.

> MemPalace does not require an API key. It is a local tool.

To verify the installation:

```bash
.venv/bin/python -c "import mempalace; print('OK')"
```

---

## 5. Verify binary availability

After installation, the `mempalace` CLI should be available inside the virtual environment:

```bash
ls .venv/bin/mempalace
```

Run it via `uv run` (which automatically uses the local `.venv`):

```bash
uv run --python .venv/bin/python mempalace --help
```

---

## 6. Path conventions used in this repo

All scripts in `scripts/` use the following pattern:

```bash
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
uv run --python "$VENV_PYTHON" mempalace <command>
```

This ensures:
- The correct Python interpreter is used regardless of what `python` or `python3` points to globally
- The virtual environment is always resolved relative to the repository root
- `uv` handles subprocess environment correctly

---

## 7. One-command setup

If you prefer, run the bootstrap script which handles steps 3–5 automatically:

```bash
bash scripts/bootstrap.sh
```

---

## 8. Next steps

After installation:

```bash
bash scripts/init_palace.sh       # Initialize MemPalace
bash scripts/mine_sample_data.sh  # Index the example notes
bash scripts/verify_install.sh    # Confirm everything works
```

---

## 9. Canonical and runtime paths

The bridge can be cloned anywhere. The installer (`setup.sh`) exposes stable,
location-independent paths in two layers:

```
Canonical per-user link:  $HOME/.local/share/mempalace-mcp-bridge
                          (a symlink to the real clone, via scripts/link_bridge.sh)

Universal runtime paths:  /opt/mempalace-mcp-bridge  ->  the canonical link
                          /mempalace                 ->  $HOME/.mempalace
                          (via scripts/runtime_aliases.sh)
```

The runtime paths are what the generated `.mcp.json` references, and they are the
reason the **same** `.mcp.json` works both on the host and inside a DevContainer:
in a container the two runtime paths are bind mounts instead of symlinks.

`/opt` and `/` are root-owned on a standard Linux host, so creating the runtime
aliases for the first time genuinely requires elevated rights. `setup.sh` runs in
the default `auto` mode and **may therefore prompt for your sudo password**; an
alias that is already correct is a no-op and prompts for nothing. `update.sh`
runs in `diagnose` mode: it never escalates and stops with instructions instead.
A partially applied state is impossible — both aliases are planned and validated
before anything is mutated.

The palace stays separate and host-owned under `$HOME/.mempalace`.

See [runtime_paths.md](runtime_paths.md) for the full contract and
[canonical_link.md](canonical_link.md) for the canonical link semantics.
