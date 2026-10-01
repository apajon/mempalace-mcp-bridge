# Update Workflow

This document covers how to keep MemPalace and this repository up to date after the initial setup.

---

## Updating

When MemPalace publishes new releases, or when this repo gets new commits, run:

```bash
git pull
bash update.sh
```

Then reload your VS Code window (`Ctrl+Shift+P` → **Developer: Reload Window**).

---

## What `update.sh` does

| Action | Notes |
|--------|-------|
| `git pull` | Pulls the latest changes from this repo |
| Ensures the canonical bridge link | `scripts/link_bridge.sh` — `$HOME/.local/share/mempalace-mcp-bridge` |
| Ensures the runtime aliases | `scripts/runtime_aliases.sh --sudo=diagnose` — `/opt/mempalace-mcp-bridge` and `/mempalace` |
| Upgrades MemPalace in `.venv` | `uv pip install --upgrade "mempalace>=3.0.0" "chromadb>=0.6,<0.7"` |
| Enforces supported ChromaDB line | Fails fast unless installed `chromadb` is on the tested `0.6.x` line |
| Checks palace health | Auto-repairs a legacy `{}` palace **only** when the strict legacy invariants hold; otherwise stops with an explicit command |
| Checks `.mcp.json` | Converges to the universal config, preserving other servers/keys |
| Runs `verify.sh` | Confirms the full stack is still healthy |

## What `update.sh` does NOT do

- **Never touches `~/.mempalace/palace`** — your notes and memories are always preserved
- Does not delete or recreate `.venv`
- Does not overwrite `.mcp.json` if the paths are still correct

---

## When to re-run `setup.sh`

Re-run `setup.sh` only if your environment is severely broken (e.g. `.venv` deleted,
`uv` uninstalled). `setup.sh` is also idempotent — it will skip steps that are
already complete, including skipping MCP config regeneration if the paths are correct.

---

## Edge cases

| Situation | What happens |
|-----------|-------------|
| Repo moved to a different path | `update.sh` re-points the canonical symlink and the runtime aliases, then regenerates `.mcp.json` |
| `/opt/mempalace-mcp-bridge` or `/mempalace` was removed | `update.sh` never escalates: it stops and tells you to run `bash setup.sh` (the interactive installer may prompt for sudo), or to run the printed `sudo ln -s` command |
| `uv` reinstalled to a different location | Nothing to do: the config uses the bare `uv` command, not an absolute path |
| `.venv` partially broken | `verify.sh` fails; re-run `bash setup.sh` to repair |
| MemPalace introduces breaking changes | `verify.sh` reports failures with actionable messages |
| Latest `chromadb` release is incompatible with existing palaces | `update.sh` keeps Chroma on the tested `0.6.x` line and fails if the environment is outside it |
| Palace was created under a different environment | `verify.sh` reports manifest drift as a warning so you can review the mismatch before trusting the palace |
| Palace has an untyped `{}` config that matches the documented legacy shape | `update.sh` backs up the SQLite file and applies the narrow legacy repair automatically |
| Palace has an untyped `{}` config that does **not** match the legacy invariants | `update.sh` stops and prints the dedicated command (`python3 scripts/palace_legacy_repair.py <palace> --apply`); nothing is mutated |

---

## Verification

Run at any time to confirm the full stack is healthy:

```bash
bash verify.sh
```

`verify.sh` now classifies the result instead of only printing pass/fail lines:

- **SUPPORTED and healthy** — all checks passed with no drift detected
- **SUPPORTED but suspicious** — the bridge is still supported, but something no longer matches cleanly
- **UNSUPPORTED or unsafe** — the bridge should not be trusted until the failures are fixed

Healthy example:

```
[PASS] uv found: /home/user/.local/bin/uv (uv 0.x.x)
[PASS] Virtual environment found at .venv/
[PASS] Python 3.12.x in .venv is on the tested 3.12 line
[PASS] mempalace 3.x.y is importable
[PASS] chromadb 0.6.x is on the supported 0.6.x line
[PASS] mempalace CLI responds
[PASS] Sample notes found in examples/sample_notes/ (3 files)
[PASS] Workspace MCP config is the universal host/DevContainer config (.mcp.json)
[PASS] Universal runtime bridge path resolves to the bridge (/opt/mempalace-mcp-bridge)
[PASS] Universal runtime palace path resolves to a palace database (/mempalace/palace)
[PASS] MCP server starts and stays alive with the exact workspace launch command
[PASS] Palace is compatible with the supported 0.6.x runtime
[INFO]  Storage profile: chroma_1_x_migrated
       schema versions: embeddings_queue=2, metadb=6, sysdb=10
[PASS] Palace is readable
[PASS] Palace manifest exists and matches the active environment
[PASS] Palace path is outside container-local filesystems (/mempalace/palace)

 Result: SUPPORTED and healthy
```

---

## Manual server start (fallback)

VS Code handles server startup automatically. If you need to test the server manually:

```bash
bash run.sh
```

Keep the terminal open while using Copilot Chat. Press `Ctrl+C` to stop.
