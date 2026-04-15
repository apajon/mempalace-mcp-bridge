# MemPalace MCP Bridge for VS Code Copilot

Give [MemPalace](https://github.com/milla-jovovich/mempalace) a persistent local memory inside VS Code Copilot Chat.

This repo provides a plug-and-play bridge:

- one-command setup
- generated VS Code MCP config
- automatic MCP server startup through VS Code
- full-stack verification with `verify.sh`
- a stable ChromaDB `0.6.x` line for existing palaces

---

## What you get

- Persistent memory inside Copilot Chat
- Fully local — no cloud, no API key, no Docker
- Auto-start — no terminal, VS Code handles everything
- Mine your own files — query your notes, docs, and decisions
- Built-in verification — `verify.sh` checks the environment, the generated MCP config, and that the MCP server actually starts
- Palace safety checks — setup, update, verify, and runtime startup reject unsupported `chromadb` versions and keep the bridge on the tested `0.6.x` line
- Reusable across environments with a shared palace

> **Compatibility status**
> This bridge currently targets the tested ChromaDB `0.6.x` line (`chromadb>=0.6,<0.7`).
> This is intentional: newer ChromaDB `1.x` releases can break older MemPalace palaces.
> If you already rely on existing palaces, this repo prioritizes stability over latest-package tracking.
> `main` fails fast when the installed `chromadb` version is outside that supported line.

---

## Install

Download the latest release: https://github.com/apajon/mempalace-mcp-bridge/releases

---

## Who this is for

This repo is for you if:

- you want MemPalace working fast inside VS Code Copilot Chat
- you want a local setup with no manual MCP wiring
- you want a stable setup for existing palaces on Chroma `0.6.x`
- you prefer reproducibility over chasing the newest Chroma release

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/apajon/mempalace-mcp-bridge.git
cd mempalace-mcp-bridge

# 2. Setup everything (installs uv, MemPalace, mines sample data, writes VS Code config)
bash setup.sh

# 3. Open this folder in VS Code

code .
```

> **Important:** open the repository root folder in VS Code (`code .` from inside `mempalace-mcp-bridge/`). Opening a subfolder will prevent MCP from loading.

Optionally verify the generated setup before opening Copilot Chat:

```bash
bash verify.sh
```

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
- Linux / WSL2 is the tested path today
- Copilot behavior remains probabilistic even with MemPalace as the preferred context source

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
MCP Server  ← launched automatically by VS Code via .vscode/mcp.json
     │
     ▼
MemPalace
     │
     ▼
Local Memory (palace)  ← ~/.mempalace/palace
```

`setup.sh` generates `.vscode/mcp.json` with the absolute path to your `uv` binary, so VS Code can start the server without any manual configuration.

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
| Devcontainer integration | [docs/devcontainer_integration.md](docs/devcontainer_integration.md) |
| Update and verify workflow | [docs/update_workflow.md](docs/update_workflow.md) |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) |
| Structured memory example | [docs/memory_example.md](docs/memory_example.md) |
| Advanced memory strategy | [docs/advanced_memory_strategy.md](docs/advanced_memory_strategy.md) |
| MemPalace project | [github.com/milla-jovovich/mempalace](https://github.com/milla-jovovich/mempalace) |
