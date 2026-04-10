# Structured Memory Example

A minimal, concrete example of organizing memory with MemPalace.  
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
[type: shared-knowledge]
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

---

*For the full strategy, see [Advanced Memory Strategy](advanced_memory_strategy.md).*
