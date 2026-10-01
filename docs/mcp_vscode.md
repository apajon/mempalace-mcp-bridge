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

`setup.sh` generates `.mcp.json` for you. The config is deliberately
user-agnostic so that the **same file** works on the host and inside a
DevContainer:

```json
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/opt/mempalace-mcp-bridge", "python", "scripts/run_mcp_server.py"],
      "env": {
        "MEMPALACE_PALACE_PATH": "/mempalace/palace"
      }
    }
  }
}
```

A ready-to-copy example is at `examples/mcp/vscode.mcp.json`. See
[runtime_paths.md](runtime_paths.md) for the full path contract.

`/opt/mempalace-mcp-bridge` and `/mempalace` are runtime paths:

- on the host, `setup.sh` creates them as symlinks via
  `scripts/runtime_aliases.sh`;
- inside a DevContainer, they are bind mounts.

Either way, the MCP config never needs to know where the repo was cloned or what
the user's home directory is called.

If you have an older `.vscode/mcp.json`, just run:

```bash
bash setup.sh   # or: bash update.sh
```

`setup.sh` / `update.sh` consolidate it into the universal `.mcp.json` and then
remove the obsolete `.vscode/mcp.json` so its stale clone path is never picked up.

> **`uv` must be on the client's PATH.** The config uses the bare `uv` command
> (that is what makes it portable). MCP clients often launch processes in a
> limited environment, so make sure `uv` is installed in a directory that is on
> the PATH the client sees (see *What to do if uv is not found* below).

---

## Working directory

`uv run --directory /opt/mempalace-mcp-bridge python scripts/run_mcp_server.py` is
run from the universal runtime bridge path so the guarded launcher can enforce
the supported ChromaDB line and the palace safety gate before starting
`mempalace.mcp_server`.

`/opt/mempalace-mcp-bridge` resolves to the real clone through the canonical
symlink `$HOME/.local/share/mempalace-mcp-bridge`, which `setup.sh` creates (see
[canonical_link.md](canonical_link.md) and [runtime_paths.md](runtime_paths.md)).
You never need to hard-code the clone location.

If the server starts but returns nothing, ensure `mempalace init` was run in or
near the workspace that the MCP client opens.

---

## What to do if uv is not found

The universal config uses the bare `uv` command, so `uv` must be resolvable on
the PATH that the MCP client sees.

1. Find where `uv` is installed:

```bash
which uv
# /home/yourname/.cargo/bin/uv
```

2. If `uv` is not installed at all, install it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Make sure the directory that contains `uv` is on the PATH the MCP client
   inherits (`~/.cargo/bin` or `~/.local/bin` in a typical install). Reload
   VS Code after changing your shell environment.

`verify.sh` reports `[FAIL] ... must launch 'uv' ...` if the config was
customised to embed an absolute `uv` path, and `bash setup.sh` restores the
portable config.

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
