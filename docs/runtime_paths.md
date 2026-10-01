# Runtime paths — one `.mcp.json` for host and DevContainer

This document defines the path contract that makes a **single, user-agnostic
`.mcp.json`** work both on the host and inside a DevContainer. It supersedes the
older "host uses the canonical link, DevContainer uses its own paths" guidance.

---

## The contract

| Role | Path | Owner |
|---|---|---|
| Real bridge clone | anywhere (e.g. `~/git/mempalace-mcp-bridge`) | you |
| **Canonical host repository** | `$HOME/.local/share/mempalace-mcp-bridge` | `scripts/link_bridge.sh` |
| **Universal runtime bridge path** | `/opt/mempalace-mcp-bridge` | `scripts/runtime_aliases.sh` (host) / bind mount (container) |
| **Palace storage (host)** | `$HOME/.mempalace` | host |
| **Universal runtime palace path** | `/mempalace/palace` | `scripts/runtime_aliases.sh` (host) / bind mount (container) |

On the host, after `setup.sh`:

```
/opt/mempalace-mcp-bridge  ->  $HOME/.local/share/mempalace-mcp-bridge  ->  <real clone>
/mempalace                 ->  $HOME/.mempalace
```

therefore:

```bash
readlink -f /opt/mempalace-mcp-bridge   # -> the real clone
readlink -f /mempalace/palace           # -> $HOME/.mempalace/palace
```

---

## The universal `.mcp.json`

`scripts/mcp_config.sh --ensure` converges `.mcp.json` to exactly this shape:

```json
{
  "servers": {
    "mempalace": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/opt/mempalace-mcp-bridge",
        "python",
        "scripts/run_mcp_server.py"
      ],
      "env": {
        "MEMPALACE_PALACE_PATH": "/mempalace/palace"
      }
    }
  }
}
```

Properties this config guarantees:

- **No user-specific path.** No `/home/<user>`, no clone path, no
  `$HOME/.local/share/...`. The same file is valid on any machine and in any
  container.
- **Bare `uv` launcher.** `uv` must be resolvable on the MCP client's `PATH`.
- **Official launcher only.** `scripts/run_mcp_server.py`, never
  `python -m mempalace.mcp_server`. The launcher enforces the ChromaDB version
  gate and the palace safety gate before the MCP server starts.
- **Explicit palace.** `MEMPALACE_PALACE_PATH` overrides any `config.json`
  inherited from another machine. Priority:
  `MEMPALACE_PALACE_PATH` > `~/.mempalace/config.json` > default.

`mcp_config.sh` only ever rewrites `servers.mempalace`. Every other server,
top-level key, and unrelated key inside the mempalace entry is preserved.

---

## Host behaviour — `scripts/runtime_aliases.sh`

```bash
bash scripts/runtime_aliases.sh                  # ensure both aliases
bash scripts/runtime_aliases.sh --status         # report the current state
bash scripts/runtime_aliases.sh --non-interactive
bash scripts/runtime_aliases.sh --sudo=diagnose  # never escalate
bash scripts/runtime_aliases.sh --no-sudo        # alias of --sudo=diagnose
bash scripts/runtime_aliases.sh --print-manual
```

Per alias, the behaviour is:

| State of the alias | Behaviour |
|---|---|
| absent | create the symlink |
| symlink already correct | success — no destructive action |
| broken symlink | re-point to the expected target |
| symlink to an old/other location | report the old target, re-point (the old target is **never** deleted) |
| real directory or regular file | **stop** with an explicit error — nothing is removed |
| parent not writable | escalate according to the sudo mode below, otherwise print the exact manual command and exit non-zero |

### Privilege model

`/opt` and `/` are root-owned on a standard Linux host, so creating these two
aliases usually needs root. The sudo behaviour is explicit and selectable:

| Mode | Behaviour |
|---|---|
| `auto` *(default)* | interactive `sudo` when stdin is a TTY, otherwise `sudo -n` |
| `interactive` | `sudo` may prompt for a password; requires a TTY, otherwise a hard error |
| `non-interactive` | `sudo -n` only — never prompts, can never hang |
| `diagnose` | never escalate; a required privilege is reported with instructions (`never` / `--no-sudo` are aliases) |

Select with `--sudo=MODE`, or the shorthands `--interactive`,
`--non-interactive`, `--no-sudo`. `MEMPALACE_RUNTIME_SUDO` and
`MEMPALACE_RUNTIME_ALLOW_SUDO=0` are the environment equivalents.

**On a fresh, standard Linux host, root really is required.** `/opt` and `/` are
not writable by a normal user, so creating the two aliases for the first time
genuinely needs `sudo`. That is expected, not something to work around. What the
policy controls is *who is allowed to ask for the password*:

- **`setup.sh` → `auto`.** This is the interactive installer, so it may prompt
  for your sudo password. A normal user with working `sudo` therefore never has
  to copy/paste commands.
- **`update.sh` → `diagnose`.** A routine update must never stop and wait for a
  password, and must not silently mutate machine-level paths either. If the
  aliases are already correct it is a no-op; if root is genuinely required it
  fails with an explicit message telling you to re-run `bash setup.sh` (or to run
  the printed `sudo ln -s` command yourself).
- **CI / automation → `--no-sudo` or `--sudo=diagnose`.**

Two guarantees:

- An alias that is already correct is a **no-op** and never looks for privileges,
  so a correctly installed machine never sees a `sudo` prompt at all.
- Both aliases are **planned first**, the required privileges are verified for
  every planned mutation, and only then is anything mutated. A missing privilege
  therefore never leaves a half-applied state (e.g. the bridge alias created but
  the palace alias missing).

If an alias cannot be ensured, the installation fails loudly with the exact
manual command, because the universal `.mcp.json` would not work without it.

### Overrides (testing / unusual layouts)

| Variable | Default | Purpose |
|---|---|---|
| `MEMPALACE_RUNTIME_BRIDGE_PATH` | `/opt/mempalace-mcp-bridge` | runtime bridge alias |
| `MEMPALACE_RUNTIME_PALACE_ROOT` | `/mempalace` | runtime palace root alias |
| `MEMPALACE_RUNTIME_PALACE_PATH` | `/mempalace/palace` | palace path written into `.mcp.json` |
| `MEMPALACE_RUNTIME_ALLOW_SUDO` | `1` | set to `0` to forbid `sudo` entirely |

These exist so the test suite can run without root; they are not part of the
normal user contract.

---

## DevContainer behaviour

Inside the container the two runtime paths are **bind mounts**, not symlinks:

```json
{
  "mounts": [
    "source=${localEnv:HOME}/.local/share/mempalace-mcp-bridge,target=/opt/mempalace-mcp-bridge,type=bind,consistency=cached,readonly",
    "source=${localEnv:HOME}/.mempalace,target=/mempalace,type=bind"
  ]
}
```

Because the mount targets are exactly the universal runtime paths, **the same
`.mcp.json` works inside the container without modification.** There is no
`<container-user>` substitution and no container-specific config.

See [devcontainer_integration.md](devcontainer_integration.md) for the full
setup.

---

## Migration from older configs

`mcp_config.sh --ensure` migrates the known legacy shapes automatically:

| Legacy shape | Migrated to |
|---|---|
| `command` = absolute path to `uv` | `command: "uv"` |
| `--directory` = the canonical link or the physical clone path | `--directory: "/opt/mempalace-mcp-bridge"` |
| `args` = `[..., "python", "-m", "mempalace.mcp_server"]` | `[..., "python", "scripts/run_mcp_server.py"]` |
| missing / `$HOME/.mempalace/palace` / `/home/<user>/.mempalace/palace` env | `MEMPALACE_PALACE_PATH: "/mempalace/palace"` |
| legacy `.vscode/mcp.json` | removed after consolidation into `.mcp.json` |

Run `bash setup.sh` (or `bash update.sh`) once and the config converges. A second
run rewrites nothing.
