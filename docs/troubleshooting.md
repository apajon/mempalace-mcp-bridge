# Troubleshooting

---

## uv not found

**Symptom:** `uv: command not found`

**Cause:** `uv` is not installed or not in `$PATH`.

**Fix:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc   # or ~/.zshrc
which uv
```

If `uv` was just installed but still not found:

```bash
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
```

Add that line to your shell rc file for persistence.

---

## mempalace not found

**Symptom:** `mempalace: command not found` or `ModuleNotFoundError: No module named 'mempalace'`

**Cause:** MemPalace was not installed into the virtual environment, or you are using the wrong Python.

**Fix:**

```bash
bash scripts/bootstrap.sh
# then verify:
.venv/bin/python -c "import mempalace"
```

Always use `uv run --python .venv/bin/python` instead of the global `python` or `mempalace`.

---

## Inconsistent virtual environment

**Symptom:** Packages seem installed but import fails, or the wrong Python version is used.

**Fix:** Delete and recreate the environment:

```bash
rm -rf .venv
bash scripts/bootstrap.sh
```

---

## No data found / empty search results

**Symptom:** `mempalace search "..."` returns nothing.

**Cause:** `mempalace mine` was never run, or it was run on the wrong directory.

**Fix:**

```bash
uv run --python .venv/bin/python mempalace mine ./examples/sample_notes/
# or for your own notes:
uv run --python .venv/bin/python mempalace mine /path/to/your/notes/
```

---

## Wrong MCP config

**Symptom:** MCP server not showing up in the client, or "server failed to start" error.

**Checklist:**

- Is `.mcp.json` at the workspace root and shaped like the universal config?
  It must use `"command": "uv"`, `--directory /opt/mempalace-mcp-bridge`,
  `python scripts/run_mcp_server.py`, and
  `env.MEMPALACE_PALACE_PATH=/mempalace/palace`.
  The quickest fix is `bash setup.sh` (or `bash update.sh`), which converges the
  file while preserving your other MCP servers.
- Is `uv` on the PATH the client sees? `which uv`
- Did you reload/restart the MCP client after editing the config?
- Does the config use `"type": "stdio"`?

---

## `error: No such file or directory (os error 2)` when starting the server

**Symptom:** The client reports the MCP server exited immediately with
`error: No such file or directory (os error 2)` and exit code `2`.

**Cause:** The universal config launches
`uv run --directory /opt/mempalace-mcp-bridge ...`, but on this machine the
runtime alias `/opt/mempalace-mcp-bridge` does not exist. This typically happens
on an older installation that only created the canonical per-user link.

**Fix:**

```bash
bash scripts/runtime_aliases.sh --status    # inspect both runtime aliases
bash setup.sh                               # or: bash update.sh
```

`setup.sh` / `update.sh` create `/opt/mempalace-mcp-bridge` and `/mempalace`. On
a fresh, standard Linux host this genuinely needs root: `/opt` and `/` are not
writable by a normal user.

- `setup.sh` uses the default `auto` mode: if stdin is a TTY it **may prompt you
  for your sudo password**, so a normal user with working `sudo` never has to
  copy/paste commands. An alias that is already correct is a no-op and prompts
  for nothing.
- `update.sh` runs with `--sudo=diagnose`: it never escalates and never waits for
  a password. If the aliases are already correct it is a no-op; if root is
  required it stops and tells you to run `bash setup.sh` (or the printed command).

If the aliases cannot be created, the exact commands to run manually are printed,
for example:

```bash
sudo ln -s -- "$HOME/.local/share/mempalace-mcp-bridge" /opt/mempalace-mcp-bridge
sudo ln -s -- "$HOME/.mempalace" /mempalace
```

Verify afterwards:

```bash
readlink -f /opt/mempalace-mcp-bridge   # -> the real clone
readlink -f /mempalace/palace           # -> $HOME/.mempalace/palace
```

---

## MCP client does not trust the server

**Symptom:** Server starts but no tools are made available, or a permission dialog appears.

**Fix:** Accept/trust the server when prompted by your MCP client. In VS Code with Copilot Chat, you may need to explicitly enable third-party MCP servers in settings.

---

## Empty memory base

**Symptom:** MemPalace is running but always returns empty results.

**Cause:** `mempalace init` may not have been run, or was run in a different directory than where the server is running.

**Fix:**

```bash
bash scripts/init_palace.sh
bash scripts/mine_sample_data.sh
```

Check where MemPalace stores its data:

```bash
ls ~/.mempalace/
```

---

## Files mined from the wrong directory

**Symptom:** Mining succeeded but wrong content appears in search results.

**Fix:** Re-run mining with the correct path:

```bash
uv run --python .venv/bin/python mempalace mine /correct/path/to/notes/
```

Note that mining is additive — previously mined content may still be present.

---

## MCP server crashes on startup

**Symptom:** The client reports the MCP server exited immediately.

**Debugging steps:**

```bash
# Run the server manually to see output:
bash scripts/run_manual_mcp.sh

# Or directly:
uv run --python .venv/bin/python python scripts/run_mcp_server.py
```

Check for Python tracebacks. Common causes:
- MemPalace not installed in the venv
- Missing configuration (init not run)
- Incompatible Python version

---

## File permissions

**Symptom:** `Permission denied` when running scripts.

**Fix:**

```bash
chmod +x scripts/*.sh
```

---

## ChromaDB version incompatibility (`No palace found`) {#chromadb-version-incompatibility}

**Symptom:** All MCP tools return:

```json
{ "error": "No palace found", "hint": "Run: mempalace init <dir> && mempalace mine <dir>" }
```

…even though the palace was working before, and `~/.mempalace/palace/` exists.

**Cause:**

ChromaDB ≥ 0.6.0 changed the internal format of the `config_json_str` column in
`~/.mempalace/palace/chroma.sqlite3`. Palaces created with an older version store
an empty JSON object (`{}`), but the new version expects a `_type` field
(`"CollectionConfigurationInternal"`). Without it, ChromaDB raises a `KeyError` during
startup, and MemPalace silently returns `"No palace found"`.

More recently, `chromadb` 1.x can also break older palaces during startup with errors like:

```text
Error executing plan: Error sending backfill request to compactor: Error reading from metadata segment reader: error occurred while decoding column 0: mismatched types; Rust type `u64` (as SQL type `INTEGER`) is not compatible with SQL type `BLOB`
```

This typically surfaces **after running `bash update.sh`** with an older bridge checkout
or after manually upgrading the `chromadb` package.

The stable `main` branch now hard-fails when installed `chromadb` is outside the supported
`0.6.x` line instead of trying to continue on an untested version.

**Automatic fix:**

```bash
bash verify.sh
```

`verify.sh` classifies the palace using the format detector and the narrow
legacy-repair preflight.

There are two distinct situations, and they are handled differently:

1. **The palace matches the narrow legacy contract.** It stores an untyped
   `config_json_str` of exactly `{}`, its SQLite integrity check passes, its
   schema/migrations match the known legacy chain, and its `seq_id` columns store
   integers. In that case `update.sh` / `setup.sh` create a consistent backup
   next to the database (via the SQLite backup API, with a timestamped name that
   never overwrites an existing backup) and rewrite only the
   `collections.config_json_str` values, inside a transaction. The palace is then
   re-detected and opened through the real stack as a smoke test.

   ```bash
   bash update.sh
   # or, to see the preflight first:
   python3 scripts/palace_legacy_repair.py ~/.mempalace/palace
   python3 scripts/palace_legacy_repair.py ~/.mempalace/palace --apply
   ```

   The contract covers **two** storage profiles, both repairable when they carry
   an untyped `config_json_str` of exactly `{}`:

   - `chroma_0_6_native` — a native 0.6.x schema (`sysdb 9` / `metadb 4`, blob
     `seq_id`, no `schema_str`, no 1.x tables);
   - `chroma_1_x_migrated` — a schema written by ChromaDB 1.x (`sysdb 10` /
     `metadb 6`, integer `seq_id`, `schema_str`, `acquire_write`,
     `embedding_metadata_array`).

   A `NULL` configuration is deliberately **not** repairable — the runtime opens a
   `NULL` config, so the palace needs nothing and is left untouched.

2. **The palace does not match that contract.** Nothing is mutated. The scripts
   stop with an explicit message listing the failing invariants:

   ```text
   [ERROR] Palace format is unknown and does not match the narrow legacy repair contract.
   ```

   In that case the palace is genuinely ambiguous and must be inspected before
   anything touches it.

The format detector still classifies an untyped `{}` palace as `unknown` — that
conservatism is intentional, because an untyped config alone cannot prove the
storage line. Read and write operations stay blocked on such a palace; only the
dedicated `repair` action is authorised, and only when every invariant passes.

This bridge pins ChromaDB to the tested `0.6.x` line during setup and updates, so
re-running the latest `bash update.sh` is the safest fix when this regression appears.

If startup or verification now stops with an error like:

```text
[ERROR] unsupported chromadb 1.x.y. This stable branch supports 0.6.x only. Run: bash update.sh
```

that is the intended guardrail. This stable bridge does not support ChromaDB `1.x`.

**Manual fix** (only if the bridge scripts are unavailable):

> Prefer the dedicated, invariant-checked command:
> `python3 scripts/palace_legacy_repair.py ~/.mempalace/palace --apply`.
> It creates a timestamped backup and rolls back on failure. The snippet below
> performs the equivalent edit by hand and is intentionally generic.

```bash
python3 - <<'EOF'
import sqlite3, json, shutil
from pathlib import Path

db = Path.home() / ".mempalace/palace/chroma.sqlite3"
shutil.copy2(db, str(db) + ".bak")   # safety backup

correct = json.dumps({
    "hnsw_configuration": {
        "space": "l2", "ef_construction": 100, "ef_search": 100,
        "num_threads": 12, "M": 16, "resize_factor": 1.2,
        "batch_size": 100, "sync_threshold": 1000,
        "_type": "HNSWConfigurationInternal"
    },
    "_type": "CollectionConfigurationInternal"
})

conn = sqlite3.connect(str(db))
c = conn.cursor()
c.execute("SELECT id, config_json_str FROM collections")
for col_id, cfg in c.fetchall():
    if not json.loads(cfg or "{}").get("_type"):
        c.execute("UPDATE collections SET config_json_str = ? WHERE id = ?", (correct, col_id))
        print(f"Fixed collection {col_id}")
conn.commit()
conn.close()
print("Done.")
EOF
```

**Verify the repair:**

```bash
bash verify.sh
# Expected: [PASS] Palace accessible (N drawers)
```

**Your data is safe:** this fix only updates a configuration field. No drawers, wings, or
knowledge graph entries are affected.
