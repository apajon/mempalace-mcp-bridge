# MemPalace MCP Bridge for VS Code Copilot

Give [MemPalace](https://github.com/milla-jovovich/mempalace) a permanent memory inside VS Code Copilot Chat — in under 2 minutes.

---

## Why this exists

MemPalace is powerful, but not plug-and-play in real workflows.
This repo fixes that.

In practice, getting it running means installing `uv` manually, writing MCP JSON configs with absolute paths, running `init` and `mine` by hand, and restarting VS Code hoping the server actually starts.

That friction stops most users before they get any value.

**This repo removes that friction.** One command installs everything, generates the config, mines sample data, and verifies the full stack. Setup takes about 2 minutes.

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

# 4. Open Copilot Chat (Ctrl+Alt+I) and ask:
#    "What architecture decisions have I documented?"
```

VS Code auto-starts the MemPalace MCP server when Copilot Chat opens.

> **Important:** open the repository root folder in VS Code (`code .` from inside `mempalace-mcp-bridge/`). Opening a subfolder will prevent MCP from loading.

You can stop here — setup is complete. Advanced usage is optional.

---

## What you get

- **Fully local** — no cloud, no API key, no Docker
- **Auto-start** — VS Code launches the MCP server automatically, no terminal needed
- **Mine your own files** — point it at any folder and Copilot can query your notes, decisions, and docs
- **Portable** — works across local and containerized environments with a shared palace

To mine your own notes after setup:

```bash
uv run --directory . mempalace mine /path/to/your/project
```

Then ask Copilot about anything in those files.

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
