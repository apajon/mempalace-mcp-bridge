# Architecture Overview

This document explains how MemPalace fits into the local development stack when used with an MCP-compatible chat client.

---

## What MemPalace is (and is not)

**MemPalace is a local memory layer**, not a chatbot and not an LLM.

It:
- Mines text files (Markdown, code, notes) into a local vector store
- Exposes a MCP server so that chat clients can query that memory during conversations
- Runs entirely on your machine — no data leaves your environment
- Requires no API key

It does not:
- Replace or augment the LLM itself
- Provide a chat interface
- Automatically appear in every chat session — it must be configured as a MCP server

---

## Data flow

```
Source files (Markdown, code, notes)
        │
        ▼
 mempalace mine <path>
        │
        ▼
Local vector store (~/.mempalace/ or configured path)
        │
        ▼
 python scripts/run_mcp_server.py ◄── guarded launcher started by MCP client
        │
        ▼
MCP client (VS Code / Copilot Chat / other)
        │
        ▼
 User sends a message in chat
        │
        ▼
 MCP tool call: mempalace.search(query)
        │
        ▼
 Retrieved memory snippets injected into LLM context
        │
        ▼
 LLM produces response enriched with local memory
```

---

## Components

| Component | Role |
|---|---|
| `uv` | Python environment and package manager |
| `mempalace` CLI | Indexes files into local memory |
| `scripts/run_mcp_server.py` | Enforces the supported ChromaDB line and the palace safety gate, then starts the MCP server |
| `scripts/link_bridge.sh` | Maintains the canonical symlink `$HOME/.local/share/mempalace-mcp-bridge` |
| `scripts/runtime_aliases.sh` | Maintains the universal runtime paths `/opt/mempalace-mcp-bridge` and `/mempalace` |
| `scripts/palace_format_detector.py` | Classifies a palace's storage line without opening it (runtime compatibility) |
| `scripts/palace_legacy_repair.py` | Detects the storage *profile* (what wrote the schema), runs the fail-closed repair preflight and the narrow legacy repair (`{}` → typed config) |
| `scripts/palace_safety_gate.py` | Refuses unsafe stable-path operations; authorises only the narrow legacy repair |
| `mempalace.mcp_server` | Exposes memory as MCP tools |
| MCP client | Launches the server, sends tool calls |
| LLM (remote) | Generates responses using memory context |

---

## Auto-start sequence

1. User opens a chat session in the MCP-compatible client
2. Client reads `.mcp.json` (or equivalent config)
3. Client launches `uv run --directory /opt/mempalace-mcp-bridge python scripts/run_mcp_server.py` as a subprocess (the universal runtime bridge path, which resolves to the real clone)
4. Server enforces the ChromaDB version gate and the palace safety gate
5. Server starts in stdio mode and waits for MCP protocol messages
6. When the user asks a question, the client may call `mempalace` tools
7. Tools return relevant memory chunks
8. These chunks are included in the LLM prompt
9. LLM responds with context-aware output
10. When the session ends, the server process is killed and will be restarted next time

---

## Local data storage

MemPalace stores its indexed data locally. Default location:

```
~/.mempalace/
```

The contents are not versioned (excluded by `.gitignore`). If you delete this directory, you need to re-run `mempalace mine`.

During initialization, the bridge writes `mempalace-bridge-manifest.json` into the palace root. This is a narrow safety artifact, not a general config layer: it captures creation-time versions plus the storage compatibility line so future tooling can identify bridge-created palaces and reason about older storage more safely.

### Bridge path vs palace path

The bridge repository may be cloned anywhere. Installation exposes two layers of
stable paths:

- the canonical per-user link — `$HOME/.local/share/mempalace-mcp-bridge` — a
  symlink to the real clone (see [canonical_link.md](canonical_link.md));
- the universal runtime paths — `/opt/mempalace-mcp-bridge` and `/mempalace` —
  which are symlinks on the host and bind mounts in a DevContainer, and are the
  paths referenced by `.mcp.json` (see [runtime_paths.md](runtime_paths.md)).

The palace remains host-owned under `~/.mempalace` and is never stored inside, or
tied to, the repository location.

---

## Copilot context strategy

**Problem:** Copilot may rely on opaque internal context, especially on first interaction with a repository.

**Solution:**

- `.github/copilot-instructions.md` — global instructions that bias context selection toward MemPalace
- `.github/instructions/mempalace-mcp-bridge.instructions.md` — scoped instructions providing project-specific conventions and memory structure

**Limitation:** Behavior is probabilistic. Instructions steer context selection but do not enforce it strictly.

---

## Why uv?

`uv` is used instead of `pip` + `venv` because:
- It creates reproducible environments faster
- It handles Python version pinning via `.python-version`
- It supports `uv run` to execute commands inside the environment without activating it
- It is the recommended approach for isolated Python tooling on Linux developer workstations
