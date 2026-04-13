---
applyTo: "**"
description: "Use when working in the mempalace-mcp-bridge project: setting up MemPalace, modifying scripts, mining memory, querying wings/rooms, writing new memory entries, debugging the MCP bridge, or managing the memory knowledge layer. Covers context-gathering order, persistence rules, deduplication policy, and entry format."
---

# MemPalace MCP Bridge — Working Context

> **Scope:** Governs how AI agents gather context and persist knowledge when working in this
> repository. The project bridges [MemPalace](https://github.com/milla-jovovich/mempalace)
> (local vector-store memory) with VS Code Copilot Chat via MCP.
> See [docs/architecture.md](../../docs/architecture.md) and
> [docs/advanced_memory_strategy.md](../../docs/advanced_memory_strategy.md) for full detail.

---

## Environment Conventions

- Python environment: always `.venv/` relative to repo root; activate with
  `source .venv/bin/activate` or use `uv run` for portability.
- Python version: 3.12 (pinned in `.python-version`; `uv` auto-respects this).
- Never use `pip install` directly — use `uv add` to add dependencies so `pyproject.toml`
  stays current.
- Setup is **idempotent**: `setup.sh` is safe to re-run; do not add one-shot guards unless
  the operation is genuinely destructive.
- Palace storage defaults to `~/.mempalace/`. Never version the index — it is `.gitignore`'d.

---

## Context Gathering

Before modifying any component, query memory in this order:

1. **Project wing** (`mempalace_mcp_bridge`) — project-specific architecture decisions,
   script contracts, known anti-patterns, and local conventions.
2. **Shared wing** (e.g., `python`, `mcp`) — general reusable knowledge: MCP protocol
   semantics, uv usage, ChromaDB patterns.
3. Merge results. Project entries override shared entries **only when explicitly marked as a
   local override**.
4. If MemPalace is unavailable, fall back to `docs/architecture.md` → `README.md` →
   workspace code search. Memory unavailability must **never** block a task.

### Retrieval Priority

```
[project wing]  →  [shared wing]  →  [local docs]  →  [code search]
       ↓
  merged context
       ↓
    decision
       ↓
  persist (if durable)
```

Conflicts: if a project entry and a shared entry conflict, the project entry wins — but only
when explicitly documented as a local override. An undocumented contradiction is a potential
inconsistency, not a silent override.

---

## Wing & Room Structure

| Wing | Room | Contents |
|------|------|----------|
| `mempalace_mcp_bridge` | `documentation` | Docs in `docs/` |
| `mempalace_mcp_bridge` | `examples` | Example configs in `examples/` |
| `mempalace_mcp_bridge` | `scripts` | Script logic and conventions |
| `mempalace_mcp_bridge` | `general` | Everything else |

Reusable, cross-project knowledge belongs in a shared wing. Project-specific decisions
belong in `mempalace_mcp_bridge`.

---

## Persistence

### What to persist

Store entries that are **durable**, **repeatable**, and **non-obvious**:

- Architecture decisions with rationale
- Script contracts and expected side-effects
- Confirmed anti-patterns (especially those that caused bugs or broken setups)
- Conventions that differ from upstream defaults
- Rules that prevent known regressions

Do **not** persist: debugging steps, temporary session results, facts already in docstrings,
one-time fixes, or speculative ideas not yet validated.

### Before writing a new entry

Search the **target wing and room** for semantically similar content before creating
anything new.

**Threshold guidance** (guidance, not enforcement):

| Similarity | Signal | Action |
|-----------|--------|--------|
| ≥ 0.86 | Near-duplicate | Enrich the existing entry; do not create a new one |
| 0.55 – 0.85 | Related content | Review manually; create only if genuinely distinct |
| < 0.55 | Likely distinct | Creating a new entry is acceptable if persistence criteria are met |

**Type-aware exception:** if two entries are similar in content but differ in type
(e.g., `architecture-rule` vs. `anti-pattern`), keep them as separate entries.

**When enriching:** preserve the original rule. Extend or qualify it rather than rewriting from
scratch. The original constraint must remain legible in the updated entry.

Use `mempalace_check_duplicate` as a secondary guard when available.

### Entry format

```
[type: architecture-rule | component-contract | anti-pattern | code-convention | migration-note]
STATUS: active
CREATED: YYYY-MM-DD

<rule or fact, one per entry>

Rationale: <why this rule exists>

[see: <wing>/<room>] — <relationship to referenced entry>  (optional)
```

### Scope assignment

- **Project wing** (`mempalace_mcp_bridge`): architecture decisions, script contracts,
  local conventions, project-specific anti-patterns.
- **Shared wing** (e.g., `python`, `mcp`): general reusable knowledge applicable across
  multiple projects.
