# setup-mempalace-mcp

A clean, reproducible setup for [MemPalace](https://github.com/thalesgroup/mempalace) using `uv`, with MCP auto-start integration for VS Code / Copilot-compatible MCP clients.

MemPalace is **not a chatbot**. It is a local memory layer: you mine your own files into it, and your MCP-compatible chat client can query that memory during conversations. No API key required.

---

## What this repo does

- Documents a clean MemPalace installation using `uv`
- Provides bootstrap scripts to set up the environment in one command
- Includes example data to mine and verify the setup
- Provides ready-to-copy MCP config for VS Code / Copilot MCP clients
- Covers auto-start mode: no terminal needed to keep the MCP server running

## What this repo does NOT do

- Does not replace your LLM or AI assistant
- Does not provide a chat UI
- Does not install GitHub Copilot or any other MCP client on your behalf
- Does not automatically configure every possible MCP client
- Does not require Docker or systemd

---

## Prerequisites

- Linux (tested on Ubuntu 24.04+, Debian, Arch)
- Python 3.12+ (managed via `uv`)
- [`uv`](https://docs.astral.sh/uv/) installed (see below)
- A MCP-compatible client (VS Code with Copilot Chat, or any stdio MCP client)

### Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then reload your shell:

```bash
source ~/.bashrc  # or ~/.zshrc
```

Verify:

```bash
uv --version
```

---

## Quickstart

```bash
# 1. Clone this repo
git clone https://github.com/yourname/setup-mempalace-mcp.git
cd setup-mempalace-mcp

# 2. Bootstrap the environment (installs MemPalace via uv)
bash scripts/bootstrap.sh

# 3. Initialize MemPalace in this directory
bash scripts/init_palace.sh

# 4. Mine the sample notes
bash scripts/mine_sample_data.sh

# 5. Copy the MCP config to your client
#    Edit examples/mcp/vscode.mcp.json (replace /ABSOLUTE/PATH/TO/uv)
#    then copy to your VS Code workspace .vscode/mcp.json

# 6. Restart your MCP client (reload VS Code window or restart Copilot Chat)

# 7. Ask a question to verify MemPalace is responding
#    e.g. "What architecture decisions have I documented?"
```

---

## Installation

### 1. Install MemPalace via uv

```bash
uv pip install mempalace
```

Or use the bootstrap script which handles everything:

```bash
bash scripts/bootstrap.sh
```

### 2. Initialize MemPalace

```bash
uv run mempalace init
```

This creates a local memory store. By default, MemPalace stores data in `~/.mempalace/` or a local path configured at init time.

### 3. Mine your files

```bash
uv run mempalace mine ./examples/sample_notes/
```

Check what was indexed:

```bash
uv run mempalace search "architecture"
```

---

## MCP Auto-Start Mode

Instead of running the MCP server manually in a terminal, configure your MCP client to launch it automatically via stdio.

The MCP server is launched with:

```bash
uv run python -m mempalace.mcp_server
```

### VS Code / Copilot Chat MCP config

Copy `examples/mcp/vscode.mcp.json` to `.vscode/mcp.json` in your workspace and replace the placeholder path:

```json
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "/ABSOLUTE/PATH/TO/uv",
      "args": ["run", "python", "-m", "mempalace.mcp_server"]
    }
  }
}
```

To find the absolute path to `uv`:

```bash
which uv
```

When the MCP client starts a session, it will automatically launch the MemPalace server as a subprocess. No terminal needed.

> **Note:** If you close the MCP client (e.g. reload VS Code), the process may stop and will be restarted on the next session. This is expected behavior for stdio MCP servers.

See [docs/mcp_vscode.md](docs/mcp_vscode.md) for full details.

---

## Verification

Run the verification script to check that everything is working:

```bash
bash scripts/verify_install.sh
```

Expected output:

```
[PASS] uv found: /home/user/.cargo/bin/uv
[PASS] mempalace installed
[PASS] mempalace responds to version check
[PASS] sample notes found in examples/sample_notes/
[PASS] All checks passed
```

---

## Manual Fallback (MCP server in terminal)

If auto-start doesn't work with your client, you can launch the server manually:

```bash
bash scripts/run_manual_mcp.sh
```

This starts the MCP server in stdio mode. Keep the terminal open while using the chat client.

See [docs/troubleshooting.md](docs/troubleshooting.md) for common issues.

---

## Frequent Errors

| Error | Likely cause |
|---|---|
| `uv: command not found` | uv not installed or not in PATH |
| `mempalace: command not found` | bootstrap.sh not run, or venv not active |
| MCP server not starting | Wrong path to `uv` in MCP config |
| No results from search | Files not mined yet, or wrong path |
| MCP tools not available | Client not configured to trust/use the server |

---

## Recommended Workflow

1. Run `bootstrap.sh` once per machine
2. Run `init_palace.sh` once per project/workspace
3. Run `mine_sample_data.sh` (or your own `mempalace mine` calls) as your notes evolve
4. Keep MCP config pointing to the right `uv` binary
5. Let the MCP client auto-start the server — no terminal management needed

---

## Repository Structure

```
.
├── README.md
├── .gitignore
├── .python-version
├── scripts/
│   ├── bootstrap.sh          # Install uv + MemPalace
│   ├── init_palace.sh        # Initialize MemPalace
│   ├── mine_sample_data.sh   # Mine example notes
│   ├── run_manual_mcp.sh     # Fallback: run MCP server manually
│   └── verify_install.sh     # Verify installation
├── docs/
│   ├── installation.md       # Detailed install guide
│   ├── mcp_vscode.md         # VS Code MCP integration
│   ├── troubleshooting.md    # Common issues
│   └── architecture.md       # How MemPalace fits in the stack
├── examples/
│   ├── sample_notes/         # Markdown files to mine
│   │   ├── decisions.md
│   │   ├── ros2_debug.md
│   │   └── architecture_notes.md
│   └── mcp/
│       ├── vscode.mcp.json           # Ready-to-copy MCP config
│       └── copilot_mcp_example.json  # Generic MCP example
└── .vscode/
    └── settings.json
```

---

## Further Reading

- [Installation guide](docs/installation.md)
- [MCP VS Code integration](docs/mcp_vscode.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Architecture overview](docs/architecture.md)
- [MemPalace documentation](https://github.com/thalesgroup/mempalace)
