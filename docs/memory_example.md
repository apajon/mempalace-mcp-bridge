# Structured Memory Example

A minimal, concrete example of organizing memory with MemPalace.  
This example shows how to separate project-specific and shared knowledge
to keep memory consistent and reusable across projects.  
For the full strategy behind this pattern, see [Advanced Memory Strategy](advanced_memory_strategy.md).

---

## Setup: Two Wings, Three Rooms

```
myapp/          ← project wing
  architecture/ ← room: project-specific design rules
  anti-patterns/← room: confirmed mistakes to avoid

react/          ← shared wing
  patterns/     ← room: general React knowledge, reusable across projects
```

The shared wing (e.g., `react`) can be reused across multiple projects,
while the project wing remains specific to a single codebase.

---

## Sample Entries

### 1. Architecture rule — project wing

**Wing:** `myapp` | **Room:** `architecture`

```
[type: architecture-rule]
STATUS: active
CREATED: 2026-03-10

All data fetching must go through the repository layer (src/repositories/).
Components must never call the API client directly.

Rationale: keeps components testable and isolates network concerns.
```

---

### 2. Anti-pattern — project wing

**Wing:** `myapp` | **Room:** `anti-patterns`

```
[type: anti-pattern]
STATUS: active
CREATED: 2026-03-18

Do not store derived state in Redux when it can be computed from existing state.
This caused a stale-data bug in the cart total after a coupon was applied.
Compute totals in selectors instead.
```

---

### 3. Shared knowledge — shared wing

**Wing:** `react` | **Room:** `patterns`

```
[type: reusable-pattern]
STATUS: active
CREATED: 2026-01-20

React Context is appropriate for low-frequency global state (theme, locale, auth).
Do not use Context for high-frequency updates (e.g., form fields, animations) —
use local state or a dedicated store instead.
```

---

## Retrieval Example

Before modifying a data-fetching component, query in this order:

```
1. myapp / architecture   → fetch the repository-layer rule
2. myapp / anti-patterns  → check for known mistakes in this area
3. react  / patterns      → fill in any shared React knowledge
```

Merge results. Project entries override shared entries only when explicitly marked
as a local override. If MemPalace is unavailable, fall back to `docs/architecture.md`,
then `README.md`.

This ensures project constraints are applied first, while still benefiting from shared knowledge.

---

## Optional: Operational rooms

When a project has meaningful runtime behavior, add operational rooms only once you
have enough real content to justify them:

```
myapp/
  incident-log/  ← specific bugs or incidents that actually happened
  debugging/     ← repeatable diagnosis commands, tools, and investigation patterns
  observability/ ← logging, metrics, traces, and correlation guidance
  failure-modes/ ← known classes of failure, triggers, and recovery strategy
```

Use them with clear boundaries:

- `incident-log` = one concrete incident, with symptoms, root cause, fix, and prevention
- `failure-modes` = generalized known risk for a component or subsystem
- `debugging` = how to inspect and diagnose
- `observability` = what signals should exist so diagnosis is possible

This keeps operational knowledge retrievable without mixing one-off incidents with
general rules or preventive instrumentation guidance.

---

## Optional: semantic deduplication

Before adding a new entry to a wing and room, check whether similar content already exists **in that same wing and room**. Scoping the comparison keeps it meaningful.

**Example using `myapp/architecture`:**

Suppose you want to add:
> "All external API calls must be wrapped in the repository layer."

Before creating it, compare against existing `myapp/architecture` entries.

- If a similar entry already exists (e.g., "Data fetching must go through `src/repositories/`"), **enrich that entry** rather than creating a parallel phrasing.
- If the existing entry covers the same constraint but is phrased differently, extend it and preserve its original rule — don't rewrite it.
- If the types differ — for example, an existing `architecture-rule` vs. a new `anti-pattern` about the same area — keep them as separate entries even if the content overlaps. They serve different purposes.

Similarity is guidance, not a gate. The primary check is always: *does this entry add something genuinely distinct?* If yes, create it. If not, enrich what exists.

> For threshold ranges and a compact reference, see [deduplication.md](deduplication.md).

---

*For the full strategy, see [Advanced Memory Strategy](advanced_memory_strategy.md).*
