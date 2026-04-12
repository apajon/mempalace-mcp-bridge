# MemPalace MCP Bridge for VS Code Copilot

Give [MemPalace](https://github.com/milla-jovovich/mempalace) a permanent memory inside VS Code Copilot Chat — in under 2 minutes.

---

## What you get

- Persistent memory inside Copilot Chat
- Fully local — no cloud, no API key, no Docker
- Auto-start — no terminal, VS Code handles everything
- Mine your own files — query your notes, docs, and decisions
- Portable — works across environments with a shared palace

---

## Install

Download the latest release: https://github.com/apajon/mempalace-mcp-bridge/releases

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/apajon/mempalace-mcp-bridge.git
cd mempalace-mcp-bridge

# 2. Setup everything (installs uv, MemPalace, mines sample data, writes VS Code config)
bash setup.sh

# 3. Open this folder in VS Code

Important: open the repository root folder (code .). Opening a subfolder will prevent MCP from loading.

# 4. Open Copilot Chat and try:

"Remember that I like Python."

Restart VS Code, then ask:

"What do you remember about me?"
```

VS Code auto-starts the MemPalace MCP server when Copilot Chat opens.

> **Important:** open the repository root folder in VS Code (`code .` from inside `mempalace-mcp-bridge/`). Opening a subfolder will prevent MCP from loading.

Setup is complete. Advanced usage is optional.

---

## Use your own data

To mine your own notes after setup:

```bash
uv run --directory . mempalace mine /path/to/your/project
```

Then ask Copilot about anything in those files.

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

`setup.sh` installs `uv` and Python 3.12 automatically.

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
