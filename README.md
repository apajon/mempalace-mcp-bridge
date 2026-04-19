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
- Palace safety checks — setup, update, verify, and runtime startup reject unsupported `chromadb` versions and keep the bridge on the supported `0.6.x` line
- Palace format safety gate — risky stable-path operations refuse palaces detected as `chroma_1_x` or `unknown`
- Palace manifest — setup writes `mempalace-bridge-manifest.json` into the palace root for version traceability
- Reusable across environments with a shared palace

> **Compatibility status**
> This bridge targets ChromaDB `0.6.x` only (`chromadb>=0.6,<0.7`).
> ChromaDB `1.x` uses an incompatible storage format; non-`0.6.x` installs are rejected at startup.
> Palaces detected as `chroma_1_x` or `unknown` format are also rejected before any operation.
> `main` fails fast when the installed `chromadb` version is outside the `0.6.x` range.

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
- No migration to ChromaDB `1.x` is provided. Non-`0.6.x` palaces are blocked at startup.
- Experimental ChromaDB `1.x` investigation work exists outside this project's stable contract and is not part of the supported bridge workflow.
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
| Devcontainer integration | [docs/devcontainer_integration.md](docs/devcontainer_integration.md) |
| Update and verify workflow | [docs/update_workflow.md](docs/update_workflow.md) |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) |
| Structured memory example | [docs/memory_example.md](docs/memory_example.md) |
| Advanced memory strategy | [docs/advanced_memory_strategy.md](docs/advanced_memory_strategy.md) |
| MemPalace project | [github.com/milla-jovovich/mempalace](https://github.com/milla-jovovich/mempalace) |
