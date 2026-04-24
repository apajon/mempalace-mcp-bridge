# MemPalace MCP Bridge

Bridge to run [MemPalace](https://github.com/milla-jovovich/mempalace) as an MCP server for VS Code Copilot Chat.

---

## What this is

- a reproducible MemPalace environment (`setup.sh`, `update.sh`, `verify.sh`)
- MCP server auto-start configuration for VS Code / Copilot Chat
- devcontainer integration (host palace mount, shared across environments)
- safe ChromaDB 0.6.x ↔ 1.x reconstruction tooling (non-destructive, runtime-validated)

This repository handles the **runtime and setup layer**. For structured memory methodology, see [Memory Engineering](#memory-engineering).

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/apajon/mempalace-mcp-bridge.git
cd mempalace-mcp-bridge

# 2. Setup (installs uv, mempalace, creates .venv, configures .mcp.json)
bash setup.sh

# 3. Verify
bash verify.sh
```

Then reload VS Code (`Ctrl+Shift+P` → **Developer: Reload Window**).

---

## MCP Configuration

The setup script generates `.mcp.json` automatically. To configure manually, create `.mcp.json` in your workspace:

```json
{
  "mcpServers": {
    "mempalace": {
      "type": "stdio",
      "command": "/ABSOLUTE/PATH/TO/uv",
      "args": ["run", "--directory", "/ABSOLUTE/PATH/TO/mempalace-mcp-bridge", "python", "scripts/run_mcp_server.py"]
    }
  }
}
```

Replace paths with the output of `which uv` and the absolute path to this repo.
A ready-to-copy example is at [`examples/mcp/vscode.mcp.json`](examples/mcp/vscode.mcp.json).

See [docs/mcp_vscode.md](docs/mcp_vscode.md) for full details and troubleshooting.

---

## Update

```bash
git pull
bash update.sh
```

`update.sh` upgrades MemPalace, enforces the pinned ChromaDB line, checks `.mcp.json` paths, and runs `verify.sh`. It never touches `~/.mempalace/palace`.

See [docs/update_workflow.md](docs/update_workflow.md) for edge cases and what the script does step by step.

---

## Verify

```bash
bash verify.sh
```

Checks that the virtual environment, MemPalace, and MCP server are all healthy. Reports actionable errors if anything is broken.

---

## Devcontainer integration

For teams using VS Code devcontainers, the palace is mounted from the host so it persists across container rebuilds.

See [docs/devcontainer_integration.md](docs/devcontainer_integration.md) for the mount design and `.devcontainer` config.

---

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md).

---

## Memory Engineering

Advanced structured memory patterns — wings, rooms, retrieval order, persistence rules, deduplication — now live in a dedicated repository:

**[mempalace-memory-engineering](https://github.com/apajon/mempalace-memory-engineering)**

This includes:
- structured memory strategy for engineering workflows
- worked examples (two-wing / three-room setup)
- semantic deduplication reference

This repository focuses solely on MCP bridge setup and runtime integration. The methodology is not duplicated here.

---

## Documentation

### Setup & runtime

* Installation: [docs/installation.md](docs/installation.md)
* MCP / VS Code config: [docs/mcp_vscode.md](docs/mcp_vscode.md)
* Update workflow: [docs/update_workflow.md](docs/update_workflow.md)
* Devcontainer integration: [docs/devcontainer_integration.md](docs/devcontainer_integration.md)
* Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)

### Architecture & internals

* Architecture overview: [docs/architecture.md](docs/architecture.md)
* Error model: [docs/error_model.md](docs/error_model.md)
* Support matrix: [docs/support_matrix.md](docs/support_matrix.md)
* Limitations: [docs/limitations.md](docs/limitations.md)

### ChromaDB reconstruction (0.6.x → 1.x)

* CLI usage: [docs/cli_usage.md](docs/cli_usage.md)
* Palace format detection: [docs/palace_format_detection.md](docs/palace_format_detection.md)
* Reconstruction workflow: [docs/chromadb_reconstruction_workflow.md](docs/chromadb_reconstruction_workflow.md)
* Migration guide: [docs/chromadb_reconstruction_migration.md](docs/chromadb_reconstruction_migration.md)

### Memory Engineering (external)

* Strategy, examples, deduplication: [mempalace-memory-engineering](https://github.com/apajon/mempalace-memory-engineering)

---

## Related

* MemPalace: [https://github.com/milla-jovovich/mempalace](https://github.com/milla-jovovich/mempalace)
* ChromaDB: [https://github.com/chroma-core/chroma](https://github.com/chroma-core/chroma)
* Memory Engineering: [https://github.com/apajon/mempalace-memory-engineering](https://github.com/apajon/mempalace-memory-engineering)

---
