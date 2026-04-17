# MemPalace MCP Bridge for VS Code Copilot

Integration layer for running MemPalace as a guarded local MCP backend in VS Code Copilot Chat on the stable ChromaDB `0.6.x` line.

---

## What this repo is

- An **integration layer** between MemPalace and VS Code Copilot Chat
- A **reproducible setup** for local MCP-backed memory
- A **guarded runtime** for the stable ChromaDB `0.6.x` line
- A **`verify.sh` path** that confirms the bridge starts and reads the palace correctly

It is **not**:

- the MemPalace engine itself
- a generic experimentation repo
- a ChromaDB `1.x` compatibility layer

## Quickstart

```bash
git clone https://github.com/apajon/mempalace-mcp-bridge.git
cd mempalace-mcp-bridge
bash setup.sh
bash verify.sh
code .
```

- Open the repository root folder in VS Code. Opening a subfolder prevents MCP from loading.
- `verify.sh` should report **SUPPORTED and healthy** before you rely on the bridge.

---

## What you get on the core path

- Workspace MCP config generated automatically in `.mcp.json`
- MCP server auto-start through VS Code / Copilot Chat
- Local MemPalace storage under the normal palace path
- Guarded launcher that rejects unsupported stable-path runtime combinations
- `verify.sh` for end-to-end verification of environment, config, startup, and palace readability
- Palace manifest for narrow version traceability
- Stable compatibility policy for existing `0.6.x` palaces

---

## Compatibility contract

This repository intentionally targets the tested ChromaDB `0.6.x` line:

- supported line: `chromadb>=0.6,<0.7`
- stable path: **ChromaDB `0.6.x` only**
- ChromaDB `1.x`: **not supported on the stable path**

The stable path prioritizes:

- preservation of existing palaces
- predictable setup
- guarded execution
- reproducible local behavior

If the active runtime is outside the supported line, the guarded path is expected to fail.

---

## Who this is for

Use this repo if:

- you want MemPalace to work inside VS Code Copilot Chat without manual MCP wiring
- you want a practical local setup, not a research project
- you want verification before relying on the bridge
- you already depend on existing palaces and want the stable `0.6.x` path

Do not use this repo as your main path if your goal is ChromaDB `1.x` experimentation.

---

## Advanced usage

Advanced material is secondary to the stable bridge path.

Mine your own data:

```bash
uv run --directory . mempalace mine /path/to/your/project
```

- Structured memory patterns: [docs/advanced_memory_strategy.md](docs/advanced_memory_strategy.md)
- Architecture overview: [docs/architecture.md](docs/architecture.md)
- VS Code / MCP details: [docs/mcp_vscode.md](docs/mcp_vscode.md)
- Devcontainer integration: [docs/devcontainer_integration.md](docs/devcontainer_integration.md)
- Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)
- Update and verify workflow: [docs/update_workflow.md](docs/update_workflow.md)

---

## Experimental: reconstruction workflow

This repo includes a separate `0.6.x` -> `1.x` reconstruction workflow.

Status:

- **experimental**
- **not part of the supported bridge path**
- **not an in-place migration tool**
- **not a supported upgrade path**

Use it only for source-preserving evaluation with a disposable target.

Documentation:

- Workflow reference: [docs/chromadb_reconstruction_workflow.md](docs/chromadb_reconstruction_workflow.md)
- Prototype details: [docs/chromadb_reconstruction_prototype.md](docs/chromadb_reconstruction_prototype.md)
- Migration assessment: [docs/chromadb_reconstruction_migration.md](docs/chromadb_reconstruction_migration.md)
- Experimental release strategy: [docs/chromadb_reconstruction_experimental_release.md](docs/chromadb_reconstruction_experimental_release.md)

Do **not** treat this as evidence that ChromaDB `1.x` is supported by the bridge.

---

## How this differs from the MemPalace core repo

**MemPalace core repo** provides the memory engine:

- mining
- storage
- retrieval
- MCP server capabilities

**This repo** provides the operating layer for a specific real workflow:

- reproducible setup
- MCP integration for VS Code Copilot Chat
- guarded runtime
- verification
- stable `0.6.x` compatibility policy

If you want the underlying memory system, use MemPalace itself:
https://github.com/milla-jovovich/mempalace

---

## Limitations

- Linux / WSL2 is the tested path today
- Copilot behavior is still probabilistic even with instructions and MCP memory available
- The stable bridge path does **not** support ChromaDB `1.x`
- Reconstruction can validate rebuilt targets experimentally, but that still does **not** make `1.x` a supported bridge target
- Automatic migration to ChromaDB `1.x` is not supported here

---

Stable release downloads:
https://github.com/apajon/mempalace-mcp-bridge/releases

---

## More docs

| Topic | Link |
|---|---|
| Palace format detection | [docs/palace_format_detection.md](docs/palace_format_detection.md) |
| Structured memory example | [docs/memory_example.md](docs/memory_example.md) |
| MemPalace project | [github.com/milla-jovovich/mempalace](https://github.com/milla-jovovich/mempalace) |
