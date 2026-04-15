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
| Upgrades MemPalace in `.venv` | `uv pip install --upgrade "mempalace>=3.0.0" "chromadb<0.7"` |
| Checks `.vscode/mcp.json` paths | Regenerates only if paths are wrong or stale |
| Runs `verify.sh` | Confirms the full stack is still healthy |

## What `update.sh` does NOT do

- **Never touches `~/.mempalace/palace`** — your notes and memories are always preserved
- Does not delete or recreate `.venv`
- Does not overwrite `.vscode/mcp.json` if the paths are still correct

---

## When to re-run `setup.sh`

Re-run `setup.sh` only if your environment is severely broken (e.g. `.venv` deleted,
`uv` uninstalled). `setup.sh` is also idempotent — it will skip steps that are
already complete, including skipping MCP config regeneration if the paths are correct.

---

## Edge cases

| Situation | What happens |
|-----------|-------------|
| Repo moved to a different path | `update.sh` detects the stale path and regenerates `.vscode/mcp.json` |
| `uv` reinstalled to a different location | Same — stale command path is detected and fixed |
| `.venv` partially broken | `verify.sh` fails; re-run `bash setup.sh` to repair |
| MemPalace introduces breaking changes | `verify.sh` reports failures with actionable messages |
| Latest `chromadb` release is incompatible with existing palaces | `update.sh` keeps Chroma on the tested `0.6.x` line automatically |
| No internet access | Version staleness check is skipped silently; update still works |

---

## Verification

Run at any time to confirm the full stack is healthy:

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

## Manual server start (fallback)

VS Code handles server startup automatically. If you need to test the server manually:

```bash
bash run.sh
```

Keep the terminal open while using Copilot Chat. Press `Ctrl+C` to stop.
