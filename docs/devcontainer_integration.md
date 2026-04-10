# MemPalace devcontainer integration

This guide explains how to make MemPalace available inside a VS Code devcontainer, with the palace shared between the host and the container.

---

## Design principles

| Element | Host side | Container side |
|---|---|---|
| **MCP bridge** (`mempalace-mcp-bridge`) | free path — defined by `MEMPALACE_BRIDGE_HOST_DIR` | mounted read-only at `/opt/mempalace-mcp-bridge` |
| **Palace** (`~/.mempalace`) | `~/.mempalace` | `~/.mempalace` of the container user |

The **host path** is flexible: each developer clones the repo wherever they like.
The **container path** is fixed: `/opt/mempalace-mcp-bridge`. Scripts, MCP config, and hooks hard-code it — no assumptions about the host machine.

> The bridge is mounted **read-only** from the host into `/opt/mempalace-mcp-bridge` inside the container. The directory must exist on the host — an empty or missing mount breaks the entire integration.

The palace is shared between the host and the container: everything the agent stores inside the container is immediately visible on the host, and vice versa.

---

## Prerequisites (host)

> The only requirement is that `MEMPALACE_BRIDGE_HOST_DIR` points to a valid local clone of `mempalace-mcp-bridge` on your host machine.

1. Clone the `mempalace-mcp-bridge` repo wherever you like:

   ```bash
   git clone https://github.com/apajon/mempalace-mcp-bridge <your-chosen-path>
   # Example: /home/alice/src/mempalace-mcp-bridge, /opt/mempalace-mcp-bridge, etc.
   ```

2. Export `MEMPALACE_BRIDGE_HOST_DIR` pointing to that clone and make it permanent:

   ```bash
   # Use an absolute path (recommended):
   export MEMPALACE_BRIDGE_HOST_DIR=/absolute/path/to/mempalace-mcp-bridge

   # Add this line to ~/.bashrc, ~/.zshrc or equivalent to make it permanent.
   ```

   > **Always use an absolute path.** The tilde `~` may not expand correctly depending on the shell environment or Docker context, causing silent mount failures.

   > **VS Code launched from a GUI does not inherit shell environment variables.** If `MEMPALACE_BRIDGE_HOST_DIR` is not visible from VS Code:
   > * either define the variable in your shell profile (`~/.bashrc`, `~/.zshrc`) and relaunch VS Code from a terminal (`code .`);
   > * or always launch VS Code from a terminal where the variable is exported.

3. Initialise the palace on the host if you haven't already:

   ```bash
   bash "$MEMPALACE_BRIDGE_HOST_DIR/setup.sh"
   ```

4. Make sure `uv` is available in the devcontainer Docker image.

---

## Step 1 — Validate the host variable (initializeCommand)

In `devcontainer.json`, add an `initializeCommand` that fails early if the variable is missing or points to a non-existent directory. The command runs **on the host**, before Docker creates the container:

```json
"initializeCommand": "test -n \"${MEMPALACE_BRIDGE_HOST_DIR}\" && test -d \"${MEMPALACE_BRIDGE_HOST_DIR}\" || (echo 'ERROR: MEMPALACE_BRIDGE_HOST_DIR is not set or does not exist. Export it to the path of your mempalace-mcp-bridge clone and rebuild.' && exit 1)"
```

No directory is created automatically. If the variable is missing or wrong, the build stops with an explicit message.

---

## Step 2 — Mount the bridge and the palace

### Option A — docker-compose.yml

```yaml
services:
  dev:
    volumes:
      # MCP bridge (read-only — venv is installed inside the container)
      - ${MEMPALACE_BRIDGE_HOST_DIR}:/opt/mempalace-mcp-bridge:ro

      # Palace shared with the host (read/write)
      - ~/.mempalace:/home/<container-user>/.mempalace
```

### Option B — devcontainer.json (without Compose)

```json
"mounts": [
  "source=${localEnv:MEMPALACE_BRIDGE_HOST_DIR},target=/opt/mempalace-mcp-bridge,type=bind,consistency=cached,readonly",
  "source=${localEnv:HOME}/.mempalace,target=/home/<container-user>/.mempalace,type=bind"
]
```

> Replace `<container-user>` with the username inside the container (`dev`, `vscode`, `user`, etc.).
> Check with `whoami` in a devcontainer terminal.

---

## Step 3 — Install dependencies and check the palace (post-create)

In `post-create.sh`, add the following block. It installs the bridge dependencies and runs the health check to detect and fix any ChromaDB incompatibilities:

```bash
MEMPALACE_DIR=/opt/mempalace-mcp-bridge

if [ -f "$MEMPALACE_DIR/pyproject.toml" ]; then
    echo 'MemPalace: installing dependencies...'
    uv sync --directory "$MEMPALACE_DIR" --quiet
    echo 'MemPalace: checking palace health...'
    bash "$MEMPALACE_DIR/scripts/check_palace_health.sh" || true
    echo 'MemPalace: ready'
else
    echo 'MemPalace: not available, skipping (set MEMPALACE_BRIDGE_HOST_DIR and rebuild the container to enable it)'
fi
```

> `uv sync` installs `mempalace` into the bridge venv **inside the container** — the `:ro` mount ensures no files are written back to the host repo.
> `check_palace_health.sh` silently fixes ChromaDB incompatibilities
> (see [troubleshooting.md#chromadb-version-incompatibility](troubleshooting.md#chromadb-version-incompatibility)).

---

## Step 4 — Configure the MCP server in VS Code

In `.vscode/mcp.json` of the devcontainer workspace:

```json
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "/home/<container-user>/.local/bin/uv",
      "args": [
        "run",
        "--directory", "/opt/mempalace-mcp-bridge",
        "python", "-m", "mempalace.mcp_server"
      ],
      "env": {
        "MEMPALACE_PALACE_PATH": "/home/<container-user>/.mempalace/palace"
      }
    }
  }
}
```

**Why `MEMPALACE_PALACE_PATH`?**
Without this variable, the MCP server looks for the palace in the current container user's home directory. The variable makes it explicit and takes priority over any `config.json` inherited from another machine.
Configuration priority: `MEMPALACE_PALACE_PATH` > `~/.mempalace/config.json` > default.

VS Code Copilot will start the MCP server automatically when the chat is opened.

---

## Summary of files to modify

| File | Change |
|---|---|
| `devcontainer.json` | Validation `initializeCommand` + `mounts` with `${localEnv:MEMPALACE_BRIDGE_HOST_DIR}` |
| `docker-compose.yml` | Bridge volume `${MEMPALACE_BRIDGE_HOST_DIR}:/opt/mempalace-mcp-bridge:ro` + palace bind mount |
| `post-create.sh` | Conditional block: `uv sync` + `check_palace_health.sh` |
| `.vscode/mcp.json` | MCP server config with `env.MEMPALACE_PALACE_PATH` |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `initializeCommand` fails: `MEMPALACE_BRIDGE_HOST_DIR is not set` | Variable not exported in the shell that launched VS Code | Add `export MEMPALACE_BRIDGE_HOST_DIR=/absolute/path/to/mempalace-mcp-bridge` to `~/.bashrc` or `~/.zshrc`, then launch VS Code from a terminal (`code .`) and rebuild |
| VS Code cannot see `MEMPALACE_BRIDGE_HOST_DIR` | VS Code launched from the GUI — it does not inherit shell environment variables | Define the variable in `~/.bashrc` or `~/.zshrc`, then launch VS Code from a terminal (`code .`) |
| `initializeCommand` fails: `does not exist` | Variable set but directory missing | Verify that `$MEMPALACE_BRIDGE_HOST_DIR` points to the root of the clone and that the clone is present |
| `MemPalace: not available, skipping` | Empty mount — `pyproject.toml` missing | Verify that `MEMPALACE_BRIDGE_HOST_DIR` points to the repo root (not a subdirectory) |
| Silently empty mount (Docker Desktop / WSL) | Windows path (`C:\...`) used instead of Linux path | Use the absolute Linux path (e.g. `/home/user/src/mempalace-mcp-bridge`) in `MEMPALACE_BRIDGE_HOST_DIR` |
| `"No palace found"` in MCP tools | Palace not mounted or `MEMPALACE_PALACE_PATH` missing/incorrect | Check the `~/.mempalace` bind mount and the `env.MEMPALACE_PALACE_PATH` key in `mcp.json` |
| Palace present on host but empty in container | Incorrect `<container-user>` in the mount or in `MEMPALACE_PALACE_PATH` | Run `whoami` inside the container and fix both occurrences of `<container-user>` |
| MCP server does not start | Incorrect `uv` path in `mcp.json` | Check with `which uv` in a devcontainer terminal and fix the `command` key |
| `uv: command not found` in container | `uv` missing from the Docker image | Add `RUN pip install uv` to the Dockerfile or via an `onCreateCommand` |
