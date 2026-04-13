# ROS 2 Architecture Context

> **Scope:** This instruction file governs how AI agents gather context and persist knowledge
> when working in a ROS 2 project that uses MemPalace as a governed knowledge layer.
> It is a concrete instance of the pattern described in
> [Advanced Memory Strategy](../docs/advanced_memory_strategy.md).

---

## Context Gathering

Before modifying any ROS 2 component, query memory in this order:

1. Query the **project wing** (e.g., `lifecore_ros2`) for project-specific architecture rules,
   component contracts, and anti-patterns.
2. Query the **shared wing** (e.g., `ros2`) for general ROS 2 knowledge — lifecycle semantics,
   communication patterns, standard conventions.
3. Merge results. Project entries override shared entries **only when explicitly marked as a
   local override**.
4. If MemPalace is unavailable, fall back to `docs/architecture.md`, then `README.md`,
   then workspace search. Memory unavailability must never block a task.

---

## Retrieval Priority

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
when it is explicitly documented as a local override. An undocumented contradiction is a
potential inconsistency, not a silent override.

---

## Persistence

### What to persist

Store entries that are **durable**, **repeatable**, and **non-obvious**:

- Architecture decisions with rationale
- Inter-component contracts
- Confirmed anti-patterns (especially those that caused bugs)
- Conventions that differ from ROS 2 defaults
- Rules that prevent known regressions

Do **not** persist: debugging steps, temporary session results, facts already in docstrings,
one-time fixes, or speculative ideas not yet validated.

### Before writing a new entry

Search the **target wing and room** for semantically similar content before creating
anything new. Scoping the comparison to the same wing and room keeps the signal relevant.

**Threshold guidance** (guidance, not enforcement):

| Similarity | Signal | Action |
|-----------|--------|--------|
| ≥ 0.86 | Near-duplicate | Enrich the existing entry; do not create a new one |
| 0.55 – 0.85 | Related content | Review manually; create only if the new entry is genuinely distinct |
| < 0.55 | Likely distinct | Creating a new entry is acceptable if persistence criteria are met |

**Type-aware exception:** if two entries are similar in content but differ in type
(e.g., `architecture-rule` vs. `anti-pattern`), keep them as separate entries.
Do not merge automatically — different types serve different purposes.

**When enriching:** preserve the original rule. Extend or qualify it rather than rewriting
it from scratch. The original constraint must remain legible in the updated entry.

Use `mempalace_check_duplicate` as a secondary guard when available.

### Entry format

```
[type: architecture-rule | component-contract | anti-pattern | code-convention | migration-note]
STATUS: active
CREATED: YYYY-MM-DD

<rule or contract, one rule per entry>

Rationale: <why this rule exists>

[see: <wing>/<room>] — <relationship to referenced entry>  (optional)
```

### Scope assignment

- **Project wing** (e.g., `lifecore_ros2`): architecture decisions, component contracts,
  local conventions, project anti-patterns.
- **Shared wing** (e.g., `ros2`): general ROS 2 knowledge reusable across projects —
  lifecycle semantics, standard message patterns, tooling conventions.

If knowledge is reusable across projects, it belongs in the shared wing, not the project wing.
Do not copy shared content into project entries; cross-reference it instead:

```
[see: ros2/lifecycle] — this component extends the state machine described there
```

---

## Guardrails

1. Do not write to memory without reading first.
2. Keep entries atomic — one entry, one rule.
3. Tag types explicitly when ambiguous.
4. Mark superseded entries as `STATUS: obsolete` or remove them.
5. Treat obsolescence as maintenance, not optional cleanup.

---

*Reference: [Advanced Memory Strategy](docs/advanced_memory_strategy.md) ·
[Deduplication](docs/deduplication.md) · [Memory Example](docs/memory_example.md)*
