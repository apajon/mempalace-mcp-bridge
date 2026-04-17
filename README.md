# MemPalace MCP Bridge for VS Code Copilot

Give [MemPalace](https://github.com/milla-jovovich/mempalace) a persistent local memory inside VS Code Copilot Chat.

This repo provides a plug-and-play bridge:

- one-command setup
- generated workspace MCP config
- automatic MCP server startup through VS Code
- full-stack verification with `verify.sh`
- a stable ChromaDB `0.6.x` line for existing palaces

---

## What you get

- Persistent memory inside Copilot Chat
- Fully local — no cloud, no API key, no Docker
- Auto-start — no terminal, VS Code handles everything
- Mine your own files — query your notes, docs, and decisions
- Built-in verification — `verify.sh` classifies the bridge as healthy, suspicious, or unsafe by checking the environment, the generated MCP config, real MCP startup, and palace manifest drift
- Palace safety checks — setup, update, verify, and runtime startup reject unsupported `chromadb` versions and keep the bridge on the tested `0.6.x` line
- Palace format safety gate — risky stable-path operations refuse palaces detected as `chroma_1_x` or `unknown`
- Palace manifest — setup writes `mempalace-bridge-manifest.json` into the palace root for version traceability
- Reusable across environments with a shared palace

> **Compatibility status**
> This bridge currently targets the tested ChromaDB `0.6.x` line (`chromadb>=0.6,<0.7`).
> This is intentional: newer ChromaDB `1.x` releases can break older MemPalace palaces.
> If you already rely on existing palaces, this repo prioritizes stability over latest-package tracking.
> `main` fails fast when the installed `chromadb` version is outside that supported line.

> **Reconstruction workflow status**
> A separate `0.6.x` → `1.x` reconstruction workflow exists only as an **experimental prototype**.
> It is **not part of the supported bridge path**, **not an in-place migration tool**, and **not a supported upgrade path**.
> Use it only for lab-style evaluation with a preserved source palace and a disposable target.

---

## Install

For the stable path, download the latest stable release:
https://github.com/apajon/mempalace-mcp-bridge/releases

Do **not** use normal stable releases for the reconstruction prototype. If an experimental
reconstruction release is published, it should be consumed only through its dedicated experimental
branch/tag and documentation.

---

## Who this is for

This repo is for you if:

- you want MemPalace working fast inside VS Code Copilot Chat
- you want a local setup with no manual MCP wiring
- you want a stable setup for existing palaces on Chroma `0.6.x`
- you prefer reproducibility over chasing the newest Chroma release

This repo is **not** for you if:

- you need official ChromaDB `1.x` support on the stable path today
- you need a one-command supported migration from `0.6.x` to `1.x`
- you cannot keep the original palace intact while evaluating a rebuilt target
- you need a guarantee that a reconstructed target will behave identically through MCP

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/apajon/mempalace-mcp-bridge.git
cd mempalace-mcp-bridge

# 2. Setup everything (installs uv, MemPalace, mines sample data, writes .mcp.json)
bash setup.sh

# 3. Open this folder in VS Code

code .
```

> **Important:** open the repository root folder in VS Code (`code .` from inside `mempalace-mcp-bridge/`). Opening a subfolder will prevent MCP from loading.

Optionally verify the generated setup before opening Copilot Chat:

```bash
bash verify.sh
```

`verify.sh` is intentionally narrow. It checks the pinned Python/Chroma environment, the installed MemPalace version, `.mcp.json` integrity, real MCP startup, palace readability, and whether the palace manifest still matches the active environment. The summary is one of:

- **SUPPORTED and healthy** — all checks passed
- **SUPPORTED but suspicious** — the bridge still works, but drift was detected and should be reviewed
- **UNSUPPORTED or unsafe** — do not rely on the bridge until the failures are fixed

---

## Test it in Copilot

```bash
# Open Copilot Chat and try:

"Remember that I like Python."

Restart VS Code, then ask:

"What do you remember about me?"
```

VS Code auto-starts the MemPalace MCP server when Copilot Chat opens.



Setup is complete. Advanced usage is optional.

---

## Use your own data

To mine your own notes after setup:

```bash
uv run --directory . mempalace mine /path/to/your/project
```

Then ask Copilot about anything in those files.

---

## Known limitations

- This bridge currently targets ChromaDB `0.6.x`, not ChromaDB `1.x`
- `main` hard-fails outside the supported `chromadb>=0.6,<0.7` range
- Existing palaces are preserved, but automatic migration to ChromaDB `1.x` is not supported here
- The reconstruction prototype can validate structure, retrieval, usage, and runtime experimentally, but that still does **not** make `1.x` a supported bridge target
- Current evidence is not strong enough to guarantee MCP usability on reconstructed `1.x` targets
- Linux / WSL2 is the tested path today
- Copilot behavior remains probabilistic even with MemPalace as the preferred context source

---

## ChromaDB `1.x` reconstruction status

**Official status: experimental.**

The repo contains a non-destructive reconstruction prototype for exporting a stable `0.6.x`
palace, rebuilding it into a separate `1.x` target, and validating the result. That prototype is
useful for investigation, but it is **not supported bridge functionality**.

For advanced evaluators, the experimental workflow now also has a single reproducible entrypoint:

```bash
./scripts/reconstruct.sh \
  --source-palace ~/.mempalace/palace \
  --target-palace /tmp/palace-target \
  --work-dir /tmp/palace-reconstruction-run \
  --source-python .venv/bin/python \
  --target-python .venv-chromadb1/bin/python
```

Add `--with-usage` and `--with-mcp-runtime` for the broader experimental checks, or `--dry-run`
to print the exact pipeline without running it. See
[`docs/chromadb_reconstruction_prototype.md`](docs/chromadb_reconstruction_prototype.md) for the
full flow, sample output, and failure examples.

### What is guaranteed

- the stable bridge path remains pinned to ChromaDB `0.6.x`
- the prototype is designed to preserve the original source palace
- reconstruction is performed into a separate target directory
- the prototype can run explicit structural, retrieval, usage, and MCP runtime checks

### What is not guaranteed

- successful reconstruction on every palace
- search-quality equivalence between source and target
- MCP runtime compatibility on reconstructed `1.x` targets
- support for historical pre-`0.6` palaces
- a supported cutover procedure

### Who should use it

- maintainers and advanced users evaluating migration feasibility
- users who can keep the source palace untouched and treat the target as disposable
- users comfortable reading validation output and making a manual go/no-go decision

### Who should not use it

- users looking for the normal setup path in this repository
- users expecting production support or stable upgrade guarantees
- users who need automatic cutover, rollback tooling, or parity guarantees

### User-facing warnings

- do **not** overwrite the source palace
- do **not** treat a reconstructed `1.x` target as supported just because export/import succeeded
- do **not** switch Copilot/MCP to a reconstructed target without passing all relevant validation
- do **not** assume retrieval parity implies MCP runtime parity

See:

- [docs/chromadb_reconstruction_prototype.md](docs/chromadb_reconstruction_prototype.md)
- [docs/chromadb_reconstruction_migration.md](docs/chromadb_reconstruction_migration.md)
- [docs/chromadb_reconstruction_experimental_release.md](docs/chromadb_reconstruction_experimental_release.md)

---

## Experimental release channel

If the reconstruction workflow is exposed publicly, the recommended release shape is:

- stable releases remain `0.6.x` only
- reconstruction is published only through a clearly named experimental branch/tag
- the workflow stays manual and opt-in
- stable setup/update/verify behavior remains unchanged

Recommended structure:

- stable releases: `vX.Y.Z`
- experimental reconstruction previews: `exp-reconstruction-vX.Y.Z`

Do **not** treat an experimental release as supported ChromaDB `1.x` bridge functionality.

---

## Why this exists

MemPalace is powerful, but not plug-and-play in real workflows.

Setting it up requires multiple manual steps and breaks the flow of using Copilot Chat.

That friction stops most users before they get any value.

This repo removes that friction. Setup takes about 2 minutes.

---

## How it fits together

```
VsCode Copilot Chat
     │
     ▼
MCP Server  ← launched automatically by Copilot via .mcp.json
     │
     ▼
MemPalace
     │
     ▼
Local Memory (palace)  ← ~/.mempalace/palace
```

`setup.sh` generates `.mcp.json` with the absolute path to your `uv` binary, so Copilot can start the server without any manual configuration.

If you already have a legacy `.vscode/mcp.json`, migrate it with:

```bash
jq '{mcpServers: .servers}' .vscode/mcp.json > .mcp.json
```

The same setup step writes `mempalace-bridge-manifest.json` into the palace root. The file is intentionally small and easy to inspect manually: it records the bridge version, MemPalace version, ChromaDB version, Python version, storage backend and format, the supported compatibility line, and the creation timestamp. If a valid manifest already exists, setup preserves it. If the file exists but is malformed, setup replaces it with a fresh valid manifest.

---

## Beyond setup — structured memory (optional)

The setup alone is already useful. But MemPalace works significantly better when memory is structured.

This repo includes patterns for:

- **Separating project vs. shared knowledge** — avoid polluting general knowledge with project-specific rules
- **Avoiding duplication and drift** — mine once, query from any environment
- **Consistent context across sessions** — decisions persist and remain retrievable

→ See [docs/advanced_memory_strategy.md](docs/advanced_memory_strategy.md) for the full approach.

---

## Compatibility

- Linux (tested on Ubuntu 24.04 via WSL2)
- VS Code with [GitHub Copilot Chat](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot-chat)
- `curl` required (`setup.sh` uses it to install `uv`)
- ChromaDB `0.6.x` line pinned intentionally via `chromadb>=0.6,<0.7`

`setup.sh` installs `uv` and Python 3.12 automatically.

---

## Copilot context guidance

Copilot is configured to use MemPalace as its primary context source via `.github/copilot-instructions.md`.

Query order: MemPalace project wing → shared wings → `docs/architecture.md` → `README.md` → workspace search.

This improves first-response relevance. It is not a strict guarantee — Copilot behavior is probabilistic.

---

## Docs

If you want to go deeper:

| Topic | Link |
|-------|------|
| Architecture overview | [docs/architecture.md](docs/architecture.md) |
| MCP config and VS Code integration | [docs/mcp_vscode.md](docs/mcp_vscode.md) |
| Palace format detection | [docs/palace_format_detection.md](docs/palace_format_detection.md) |
| Reconstruction workflow status and prototype | [docs/chromadb_reconstruction_prototype.md](docs/chromadb_reconstruction_prototype.md) |
| Reconstruction migration assessment | [docs/chromadb_reconstruction_migration.md](docs/chromadb_reconstruction_migration.md) |
| Experimental release strategy | [docs/chromadb_reconstruction_experimental_release.md](docs/chromadb_reconstruction_experimental_release.md) |
| Devcontainer integration | [docs/devcontainer_integration.md](docs/devcontainer_integration.md) |
| Update and verify workflow | [docs/update_workflow.md](docs/update_workflow.md) |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) |
| Structured memory example | [docs/memory_example.md](docs/memory_example.md) |
| Advanced memory strategy | [docs/advanced_memory_strategy.md](docs/advanced_memory_strategy.md) |
| MemPalace project | [github.com/milla-jovovich/mempalace](https://github.com/milla-jovovich/mempalace) |
