# MemPalace devcontainer integration

This guide explains how to make MemPalace available inside a VS Code devcontainer, with the palace shared between the host and the container.

---

## Design principle: host as source of truth

Containers are ephemeral execution environments — they do not own data. The palace must persist independently from the container lifecycle.

Mounting the palace from the host ensures consistency across:

- local tools
- devcontainers
- multiple projects

> **Warning:** without this, each environment may initialise its own palace, creating multiple independent stores that silently diverge.

---

## Design rationale

| Element | Host side | Container side |
|---|---|---|
| **MCP bridge** (`mempalace-mcp-bridge`) | `/opt/mempalace-mcp-bridge` → `$HOME/.local/share/mempalace-mcp-bridge` (symlink to the real clone) | mounted read-only at `/opt/mempalace-mcp-bridge` |
| **Palace** (`~/.mempalace`) | `$HOME/.mempalace` | mounted at `/mempalace` |

**The bridge is not cloned inside the container.** Keeping it on the host and mounting it at the universal runtime path (`/opt/mempalace-mcp-bridge`) means scripts, MCP config, and hooks always reference the same location regardless of where each developer stores the repo on their machine.

The host-side source is the **canonical bridge path** `$HOME/.local/share/mempalace-mcp-bridge`, which `setup.sh` creates as a symlink to the real clone (see [canonical_link.md](canonical_link.md)). `setup.sh` also creates the runtime alias `/opt/mempalace-mcp-bridge` pointing at it (see [runtime_paths.md](runtime_paths.md)). The real clone may live anywhere; the devcontainer never needs to know where.

**A shared palace is used** so that everything the agent stores inside the container is immediately visible on the host, and vice versa. The palace is mounted at `/mempalace`, which is the same path the host exposes through its own runtime alias. Both environments therefore address the palace as `/mempalace/palace` and no copying or syncing is needed.

**`MEMPALACE_PALACE_PATH=/mempalace/palace` is set explicitly** in `.mcp.json` to override any `config.json` that may have been inherited from another machine. This also removes any dependency on the container user's home directory.

**The `.mcp.json` file is identical host-side and container-side.** Because both sides expose `/opt/mempalace-mcp-bridge` and `/mempalace`, the same file works in both places with no `<container-user>` substitution.

> The bridge is mounted **read-only** at `/opt/mempalace-mcp-bridge`. Nothing is written back to the host repo.

---

## Prerequisites (host)

> The bridge may be cloned anywhere. The only requirement is that the normal
> bridge install has been run once, which creates the canonical symlink at
> `$HOME/.local/share/mempalace-mcp-bridge` **and** the runtime alias
> `/opt/mempalace-mcp-bridge`.

1. Clone the `mempalace-mcp-bridge` repo wherever you like:

   ```bash
   git clone https://github.com/apajon/mempalace-mcp-bridge.git ~/git/mempalace-mcp-bridge
   # ...or any other location
   ```

2. Run the normal bridge install once. This creates the canonical symlink
   `$HOME/.local/share/mempalace-mcp-bridge` pointing at the real clone, and the
   runtime aliases `/opt/mempalace-mcp-bridge` and `/mempalace` (the latter two
   may require elevated rights on `/opt` / `/`):

   ```bash
   bash ~/git/mempalace-mcp-bridge/setup.sh   # or the path where you cloned it
   ```

3. Make sure `uv` is available in the devcontainer Docker image.

---

## Step 1 — Prepare the host mount point (initializeCommand)

In `devcontainer.json`, add an `initializeCommand` that prepares the host-side directory before Docker creates the container:

```json
"initializeCommand": "mkdir -p ${HOME:-$(echo ~)}/.local/share || true"
```

This does two things:

- creates the expected host directory if it does not exist yet;
- tolerates cases where `HOME` is empty because VS Code's `userEnvProbe` timed out or the shell startup was incomplete.

The `|| true` prevents spurious devcontainer failures if the host shell environment is only partially initialised.

---

## Step 2 — Mount the bridge and the palace

In `devcontainer.json`, add the following mounts:

```json
"mounts": [
  "source=${localEnv:HOME}/.local/share/mempalace-mcp-bridge,target=/opt/mempalace-mcp-bridge,type=bind,consistency=cached,readonly",
  "source=${localEnv:HOME}/.mempalace,target=/mempalace,type=bind"
]
```

> The bridge mount source is the canonical symlink created by `setup.sh`;
> Docker resolves the symlink and mounts the real clone.
>
> The palace mount target is exactly `/mempalace` — the same path the host
> exposes through its runtime alias. That is what makes the universal
> `.mcp.json` work unchanged in both places.
>
> If `${localEnv:HOME}` is unreliable on your platform, replace it with an
> explicit absolute host path.

---

## Step 3 — Install dependencies and check the palace (post-create)

In `post-create.sh`, add the following block. It installs the bridge dependencies and runs the health check to detect and fix any ChromaDB incompatibilities:

```bash
MEMPALACE_DIR=/opt/mempalace-mcp-bridge
MEMPALACE_VENV=/home/<container-user>/.venv/mempalace-mcp-bridge

if [ -f "$MEMPALACE_DIR/pyproject.toml" ]; then
    echo 'MemPalace: installing dependencies...'
    UV_PROJECT_ENVIRONMENT="$MEMPALACE_VENV" uv sync --directory "$MEMPALACE_DIR" --quiet
    echo 'MemPalace: checking palace health...'
    bash "$MEMPALACE_DIR/scripts/check_palace_health.sh" || true
    echo 'MemPalace: ready'
else
    echo 'MemPalace: not available, skipping (run bash setup.sh on the host to create the canonical bridge link, then rebuild the container to enable it)'
fi
```

> Because the bridge is mounted `:ro`, `uv sync` must **not** try to create `.venv/` inside `/opt/mempalace-mcp-bridge`. `UV_PROJECT_ENVIRONMENT` redirects the environment to a writable path owned by the container user.
>
> `check_palace_health.sh` silently fixes ChromaDB incompatibilities
> (see [troubleshooting.md#chromadb-version-incompatibility](troubleshooting.md#chromadb-version-incompatibility)).

---

## Step 4 — Configure the MCP server in VS Code

The workspace `.mcp.json` is **the same file** on the host and in the container.
`setup.sh` generates it, and it contains no container-specific or user-specific
path:

```json
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory", "/opt/mempalace-mcp-bridge",
        "python", "scripts/run_mcp_server.py"
      ],
      "env": {
        "MEMPALACE_PALACE_PATH": "/mempalace/palace"
      }
    }
  }
}
```

**Why `MEMPALACE_PALACE_PATH`?**
Without this variable, the MCP server looks for the palace in the current user's
home directory, which differs between the host and the container. The variable
makes the palace location explicit and takes priority over any `config.json`
inherited from another machine.
Configuration priority: `MEMPALACE_PALACE_PATH` > `~/.mempalace/config.json` > default.

**Why `command: "uv"` and not an absolute path?**
An absolute `uv` path differs between the host and the container, which would
break the "same config everywhere" contract. The trade-off is that `uv` must be
resolvable on the PATH the MCP client sees. Install `uv` into the image so it is
on the default PATH (see *Prerequisites*).

VS Code Copilot will start the MCP server automatically when the chat is opened.

> Do **not** re-add a `/home/<container-user>/...` path here. If `verify.sh`
> reports that the config is not the universal config, run `bash setup.sh` (or
> `bash update.sh`) to regenerate it.

---

## Summary of files to modify

| File | Change |
|---|---|
| `devcontainer.json` | Robust `initializeCommand` + readonly mount `${localEnv:HOME}/.local/share/mempalace-mcp-bridge` → `/opt/mempalace-mcp-bridge`, and `${localEnv:HOME}/.mempalace` → `/mempalace` |
| `post-create.sh` | Conditional block: `UV_PROJECT_ENVIRONMENT=... uv sync` + `check_palace_health.sh` |
| `.mcp.json` | The universal MCP config (generated by `setup.sh`, identical on host and container) |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `initializeCommand` fails because `HOME` is empty | `userEnvProbe` timed out or shell startup did not fully initialise the environment | Use `mkdir -p ${HOME:-$(echo ~)}/.local/share || true` so the command still resolves a host home directory |
| `MemPalace: not available, skipping` | Empty mount — `pyproject.toml` missing | Verify that `$HOME/.local/share/mempalace-mcp-bridge` exists on the host and resolves to the real clone, and that the mount points to it |
| Bridge mount is empty in the container | `$HOME/.local/share/mempalace-mcp-bridge` is missing on the host or mounted from the wrong absolute path | Run `bash setup.sh` in the real clone to create the canonical symlink, or replace the mount source with the correct absolute host path |
| `uv sync` fails with a write or permission error under `/opt/mempalace-mcp-bridge` | The bridge repo is mounted read-only | Set `UV_PROJECT_ENVIRONMENT=/home/<container-user>/.venv/mempalace-mcp-bridge` before `uv sync` |
| `"No palace found"` in MCP tools | Palace not mounted at `/mempalace`, or `MEMPALACE_PALACE_PATH` missing/incorrect | Check the `${localEnv:HOME}/.mempalace` → `/mempalace` bind mount and the `env.MEMPALACE_PALACE_PATH` key in `.mcp.json` |
| Palace present on host but empty in container | The palace mount target is not `/mempalace` | Mount `${localEnv:HOME}/.mempalace` at target `/mempalace` exactly |
| MCP server does not start (host or container) | The config is not the universal config (e.g. still embeds an absolute `uv` path or a `/home/<user>` path) | Run `bash setup.sh` (or `bash update.sh`) to regenerate `.mcp.json`, then reload the window |
| `uv: command not found` in container | `uv` missing from the Docker image PATH | Install `uv` in the image (`RUN pip install uv`) so it is on the default PATH |
