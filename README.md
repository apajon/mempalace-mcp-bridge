# MemPalace MCP Bridge for VS Code Copilot

Give [MemPalace](https://github.com/milla-jovovich/mempalace) a permanent memory inside VS Code Copilot Chat — in under 2 minutes.

MemPalace lets you mine your own files into a local memory store and query that memory from any MCP-compatible client. No cloud, no API key, no Docker.  
This repo makes the entire setup plug-and-play: one command does everything.

---

## What this is not

- Not a replacement for MemPalace — it is the integration layer that makes MemPalace easy to use
- Not a generic MCP template — everything here is specific to MemPalace and VS Code Copilot
- Not a chat UI or AI assistant — just the fastest path from zero to working MemPalace in Copilot

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

That's it. VS Code will auto-start the MemPalace MCP server when Copilot Chat opens. The first time may take a few seconds while VS Code initializes the server.

> **Important:** open the repository root folder in VS Code (`code .` from inside `mempalace-mcp-bridge/`). Opening a subfolder will prevent MCP from loading.

---

<details>
<summary>Table of Contents</summary>

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Test it in Copilot](#test-it-in-copilot)
- [Why this repo exists](#why-this-repo-exists)
- [Verification](#verification)
- [Updating](#updating)
  - [What `update.sh` does](#what-updatesh-does)
  - [What `update.sh` does NOT do](#what-updatesh-does-not-do)
  - [When to re-run `setup.sh`](#when-to-re-run-setupsh)
  - [Edge cases](#edge-cases)
- [How it works](#how-it-works)
- [Shared memory across environments](#shared-memory-across-environments)
- [MCP config and paths](#mcp-config-and-paths)
- [Frequent errors](#frequent-errors)
- [Design insight](#design-insight)
- [Repository structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Further reading](#further-reading)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

</details>

## Compatibility

This setup has been tested on:

- Ubuntu 24.04 (WSL2)
- Python 3.12
- VS Code with GitHub Copilot Chat

Other Linux environments should work, but have not been explicitly tested.

The setup relies on `uv`, which manages Python and dependencies automatically.

> If you're on Windows, using WSL2 is recommended for best compatibility.

## Test it in Copilot

After setup, open Copilot Chat and try:

| Prompt | Expected result |
|--------|-----------------|
| `What architecture decisions have I documented?` | MemPalace returns decisions from `examples/sample_notes/decisions.md` |
| `What do I know about ROS2 debugging?` | MemPalace returns notes from `ros2_debug.md` |
| `Summarize my architecture notes` | MemPalace retrieves and Copilot summarizes `architecture_notes.md` |

To mine your own notes into memory:

```bash
uv run --directory . mempalace mine /path/to/your/project
```

Then ask Copilot about anything in those files.

---

## Why this repo exists

The official MemPalace setup requires:

- Manual `uv` installation
- Running `mempalace init` and `mempalace mine` by hand
- Writing a JSON MCP config with absolute paths filled in manually
- Restarting VS Code and hoping the server starts

**This repo removes all of that friction:**

- `uv`-based reproducible environment — no virtualenv juggling
- `setup.sh` does everything in one shot
- MCP config is generated automatically with the correct paths
- `verify.sh` confirms the full stack is working

---

## Verification

```bash
bash verify.sh
```

Expected output:

```
[PASS] uv found: /home/user/.local/bin/uv (uv 0.x.x)
[PASS] Virtual environment found at .venv/
[PASS] mempalace package importable
[PASS] mempalace CLI responds
[PASS] Sample notes found in examples/sample_notes/ (3 files)
[PASS] VS Code MCP config present and populated (.vscode/mcp.json)
[PASS] MCP server starts without error (exact command from .vscode/mcp.json)

 All 7 checks passed — you're ready to use MemPalace in VS Code!
```

---

## Updating

When MemPalace publishes new releases, or when this repo gets new commits, run:

```bash
git pull
bash update.sh
```

Then reload your VS Code window (`Ctrl+Shift+P` → **Developer: Reload Window**).

### What `update.sh` does

| Action | Notes |
|--------|-------|
| `git pull` | Pulls the latest changes from this repo |
| Upgrades MemPalace in `.venv` | `uv pip install --upgrade mempalace` |
| Checks `.vscode/mcp.json` paths | Regenerates only if paths are wrong or stale |
| Runs `verify.sh` | Confirms the full stack is still healthy |

### What `update.sh` does NOT do

- **Never touches `~/.mempalace/palace`** — your notes and memories are always preserved
- Does not delete or recreate `.venv`
- Does not overwrite `.vscode/mcp.json` if the paths are still correct

### When to re-run `setup.sh`

Re-run `setup.sh` only if your environment is severely broken (e.g. `.venv` deleted,
`uv` uninstalled). `setup.sh` is also idempotent — it will skip steps that are
already complete, including skipping MCP config regeneration if the paths are correct.

### Edge cases

| Situation | What happens |
|-----------|-------------|
| Repo moved to a different path | `update.sh` detects the stale path and regenerates `.vscode/mcp.json` |
| `uv` reinstalled to a different location | Same — stale command path is detected and fixed |
| `.venv` partially broken | `verify.sh` fails; re-run `bash setup.sh` to repair |
| MemPalace introduces breaking changes | `verify.sh` reports failures with actionable messages |
| No internet access | Version staleness check is skipped silently; update still works |

---

VS Code handles server startup automatically. If you need to test the server manually:

```bash
bash run.sh
```

Keep the terminal open while using Copilot Chat. Press `Ctrl+C` to stop.

---

## How it works

```
VS Code Copilot Chat
       │  MCP stdio
       ▼
mempalace.mcp_server   ← launched automatically by VS Code via .vscode/mcp.json
       │
       ▼
~/.mempalace/palace    ← local vector store of your mined files
```

`setup.sh` writes `.vscode/mcp.json` with the absolute path to your `uv` binary, so VS Code can start the server without any manual configuration.

---

## Shared memory across environments

The MemPalace store (`~/.mempalace/palace`) lives on the host machine and is shared across every environment that can reach it — your local terminal, VS Code on the host, and any devcontainer.

When working inside a devcontainer, the bridge mounts that store read-only so the container can query the same memories without duplicating or diverging them.

This means:

- **No duplication** — mine once, query everywhere
- **Consistent context** — the same notes and decisions are available whether you're in a container or on bare metal
- **Better multi-project workflows** — switch projects or environments without losing your memory

---

## MCP config and paths

`.vscode/mcp.json` is generated by `setup.sh`. It contains machine-specific absolute paths and must not be committed:

```json
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "/home/yourname/.local/bin/uv",
      "args": ["run", "--directory", "/home/yourname/mempalace-mcp-bridge", "python", "-m", "mempalace.mcp_server"]
    }
  }
}
```

Key points:

- `command` — absolute path to your `uv` binary (varies per machine)
- `--directory` — absolute path to this repo (varies per machine)
- The file is intentionally listed in `.gitignore`
- **If you move or rename the repo folder, re-run `bash setup.sh`** to regenerate the config with the correct paths

---

## Frequent errors

| Error | Fix |
|-------|-----|
| `uv: command not found` | Re-run `bash setup.sh` — it installs uv automatically |
| MCP server not starting | Run `bash verify.sh` to diagnose; check `.vscode/mcp.json` |
| No results from Copilot | Mine your files: `uv run --directory . mempalace mine <path>` |
| MCP tools not available | Reload VS Code window; ensure Copilot Chat trusts the server |
| Copilot answers but ignores MemPalace | Copilot can silently skip MCP tools — explicitly mention memory in your prompt (e.g. "using my notes, …") to force tool use |

---

## Design insight

MCP is a powerful protocol but its developer experience is rough today: JSON config files with hard-coded paths, no standard discovery, and no feedback when something silently fails. This repo is a concrete example of wrapping that friction so that a real tool — MemPalace — works immediately in a real workflow without any manual plumbing.

---

## Repository structure

```
.
├── setup.sh                  # ONE command: full setup + config generation
├── update.sh                 # Safe update: pull, upgrade, revalidate
├── run.sh                    # Start MCP server manually (fallback)
├── verify.sh                 # Verify the entire stack
├── scripts/
│   ├── bootstrap.sh          # Install uv + MemPalace
│   ├── init_palace.sh        # Initialize MemPalace
│   ├── mine_sample_data.sh   # Mine example notes
│   └── run_manual_mcp.sh     # MCP server entry point
├── examples/
│   ├── sample_notes/         # Markdown files mined on first setup
│   └── mcp/
│       └── vscode.mcp.json   # Template (setup.sh writes the real one)
├── docs/
│   ├── mcp_vscode.md         # VS Code MCP integration details
│   ├── troubleshooting.md    # Common issues
│   └── architecture.md       # How MemPalace fits in the stack
└── .vscode/
    ├── settings.json
    └── mcp.json              # Generated by setup.sh — do not edit manually
```

---

## Prerequisites

- Linux (tested on Ubuntu 24.04+, Debian, Arch)
- `curl` (to install `uv` if missing)
- VS Code with [GitHub Copilot Chat](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot-chat) extension

`setup.sh` installs `uv` and Python 3.12 automatically if they are missing.

---

## Further reading

- [MCP VS Code integration details](docs/mcp_vscode.md)
- [Devcontainer integration](docs/devcontainer_integration.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Architecture overview](docs/architecture.md)
- [Advanced usage: Structured Memory Strategy](docs/advanced_memory_strategy.md)
- [MemPalace project](https://github.com/milla-jovovich/mempalace)
