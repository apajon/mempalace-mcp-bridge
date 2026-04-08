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

- Is the path to `uv` absolute and correct?
  ```bash
  which uv
  ```
- Is the config file in the right place (`.vscode/mcp.json` for VS Code)?
- Did you reload/restart the MCP client after editing the config?
- Does the config use `"type": "stdio"`?

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
.venv/bin/python -m mempalace.mcp_server
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
