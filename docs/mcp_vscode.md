# MCP Integration — VS Code / Copilot Chat

This document explains how to configure a MCP-compatible client to automatically start the MemPalace MCP server, without needing a dedicated terminal.

---

## How auto-start works

The MCP protocol supports servers that communicate over stdio. When you configure a MCP client with a `type: stdio` server, it:

1. Launches the command as a subprocess when a chat session starts
2. Communicates with it via stdin/stdout
3. Kills the subprocess when the session ends (behavior varies by client)

This means **you never need to run `run_manual_mcp.sh` in a terminal** — the client handles everything.

---

## MCP config for VS Code / Copilot Chat

Create or edit `.vscode/mcp.json` in your workspace:

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

Replace `/ABSOLUTE/PATH/TO/uv` with the actual path to your `uv` binary:

```bash
which uv
# /home/yourname/.cargo/bin/uv
```

A ready-to-copy example is at `examples/mcp/vscode.mcp.json`.

> **Why absolute path?** MCP clients often launch processes in a limited environment where `$PATH` may not include your shell's customizations. Using an absolute path avoids "command not found" errors.

---

## Working directory

`uv run python -m mempalace.mcp_server` should be run from the directory where your MemPalace data was initialized. If your MCP client allows setting a `cwd`, set it to the repository root.

If not, ensure `mempalace init` was run in or near the workspace that the MCP client opens.

---

## What to do if uv is not found

1. Find where `uv` is installed:

```bash
which uv
# or
find ~/.cargo ~/.local -name uv 2>/dev/null
```

2. Use that absolute path in the MCP config.

3. If `uv` is not installed at all, run:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## What to do if the server starts but no tools are used

- Make sure `mempalace init` was run in the correct directory
- Make sure `mempalace mine` was called on at least one folder with files
- Check that the MCP client trusts the server (some clients prompt for permission)
- Reload the MCP client window after changing the config

---

## Verifying the MCP server starts correctly (manual test)

```bash
bash scripts/run_manual_mcp.sh
```

If the server starts without errors and waits for input, the config is correct.

---

## Process lifecycle

| Event | What happens |
|---|---|
| MCP client starts session | Server process is launched |
| Chat interaction occurs | Client sends MCP requests to server |
| MCP client closes / window reloads | Server process may be killed |
| MCP client re-opens session | Server is relaunched automatically |

This is normal stdio MCP behavior. There is no persistent daemon — the process is managed entirely by the client.
