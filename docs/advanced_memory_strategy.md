# Advanced Memory Strategy for Engineering Workflows

> **Scope notice:** This document describes one possible advanced usage pattern for MemPalace.
> It is not the official workflow, not a required approach, and not a replacement for existing documentation.
> It is a structured strategy that some teams have found effective when using MemPalace as a governed knowledge layer across multiple projects.

---

## 1. Introduction

MemPalace stores knowledge in a local vector store and exposes it to AI agents via MCP. Out of the box, that is already useful: mine a folder, ask Copilot a question, get an answer grounded in your own files.

But as projects grow, a purely flat store starts to show cracks:

- Agents retrieve outdated decisions alongside current ones
- Project-specific rules bleed into general knowledge and vice versa
- The same fact gets written multiple times in different phrasings
- A useful insight disappears into an unsearchable pile of session notes

This document proposes a **structured strategy** to prevent those problems. The core idea is simple: treat your memory store as a first-class engineering artifact, with the same discipline you would apply to a shared codebase.

---

## 2. Design Goals

A governed memory layer should satisfy these properties:

| Goal | What it means in practice |
|------|--------------------------|
| **Scoped** | Project knowledge and shared knowledge are separated |
| **Retrievable** | Agents can find the right context in a predictable order |
| **Deduplicated** | The same rule does not exist in two places with different phrasings |
| **Durable** | Decisions persist beyond session boundaries |
| **Graceful** | Agents do not break when memory is unavailable |

None of these require new tooling. They require discipline in *how* you write to and read from MemPalace.

---

## 3. Core Model: Wings, Rooms, and Entry Types

### 3.1 Wings — Namespace by Scope

A **wing** is the top-level namespace in MemPalace. The key design decision is this:

**Do not create one wing per project. Separate by scope, not by workspace.**

In practice, this means most setups land on exactly two wings: one for the current project, one for shared/transverse knowledge. That is intentional — not a limitation.

A minimal two-wing model works well for most engineering workflows:

| Wing | Scope | What goes here |
|------|-------|----------------|
| `<project_name>` | Project-specific | Architecture decisions, component contracts, local conventions, project anti-patterns |
| `<technology>` or `shared` | Transverse/shared | General knowledge about a platform, framework, or tool — reusable across projects |

Example: a team using ROS 2 might have a `lifecore_ros2` wing (project) and a `ros2` wing (shared). A web team might have `myapp` and `react`.

The rule: **if knowledge is reusable across projects, it belongs in a shared wing, not a project wing.**

### 3.2 Rooms — Categories Within a Wing

A **room** is a category within a wing. Rooms make retrieval predictable and keep memory searchable by subject.

Suggested standard room slugs (hyphenated lowercase, create only when content exists):

| Room | Purpose |
|------|---------|
| `architecture` | High-level design decisions, layer definitions |
| `components` | Component contracts, interfaces, extension points |
| `communication` | Message passing, API patterns, protocols |
| `configuration` | Config files, parameters, environment setup |
| `contracts` | Inter-component agreements, API guarantees |
| `anti-patterns` | Confirmed mistakes to avoid |
| `conventions` | Naming, style, tooling conventions |
| `validation` | Testing rules, CI gates, quality checks |
| `migration-notes` | Breaking changes, version upgrades, deprecation paths |

You do not need all of these. Start with `architecture` and `anti-patterns`. Add rooms when content justifies them.

### 3.3 Entry Types — Classify What You Store

Every entry should be classifiable. When the type is not obvious, tag it explicitly in the content:

```
[type: architecture-rule]
[type: component-contract]
[type: anti-pattern]
[type: code-convention]
[type: reusable-pattern]
[type: project-decision]
[type: migration-note]
```

This discipline pays off during retrieval: agents can filter or weigh entries by type, and reviewers can tell at a glance whether an entry is a hard constraint or an advisory note.

---

## 4. Retrieval Strategy

When an agent gathers context before making a decision or change, it should query memory in a defined priority order:

```
1. Project wing  →  project-specific rules take precedence
2. Shared wing   →  transverse knowledge fills in what the project wing lacks
3. Local docs    →  README, architecture files, inline comments
4. Code search   →  grep/symbol search as last resort
```

**Merging results:** Combine entries from both wings. If a project entry and a shared entry conflict, the project entry wins — but only if it is explicitly documented as a local override. A project entry that simply contradicts a shared rule without explanation should be treated as a potential inconsistency, not a silent override.

**Fallback behavior:** If MemPalace tools are unavailable, agents must continue silently with local sources. Memory unavailability is never a reason to block a task. Design your instruction files accordingly.

**Agent decision flow:**

```
[project wing] → [shared wing] → [local docs] → [code search]
        ↓
   merged context
        ↓
    decision
        ↓
  persist (if durable)
```

**Practical pattern for instruction files:**

```markdown
## Context Gathering

1. Query the project wing (e.g., `myproject`) for project-specific rules.
2. Query the shared wing (e.g., `platform`) for general knowledge.
3. Merge results. Project rules override shared rules only when explicitly marked.
4. If mempalace is unavailable, fall back to `docs/architecture.md`, then `README.md`, then workspace search.
```

---

## 5. Persistence Strategy

### 5.1 What to Persist

Store entries that are:

- **Durable** — will remain relevant beyond the current session
- **Repeatable** — you will want this rule enforced again in the future
- **Non-obvious** — not trivially inferred from reading the code

Good candidates:
- Architecture decisions with rationale
- Inter-component contracts
- Confirmed anti-patterns (especially ones that caused bugs)
- Conventions that differ from standard tooling defaults
- Rules that prevent known regressions

### 5.2 What NOT to Persist

Do not store:
- Debugging steps for a specific issue
- Temporary session results
- Information already present verbatim in docstrings
- One-time fixes with no recurring relevance
- Speculative ideas not yet validated

The test: *if this knowledge were lost tomorrow, would we reconstruct it and write it the same way?* If yes, persist. If no, skip.

### 5.3 Deduplication Policy

Before writing a new entry, search the target wing and room for semantically similar content.

- If an existing entry covers **80% or more** of the same information: **enrich** the existing entry rather than creating a new one.
- If the new entry supersedes an older one: mark the old entry as `STATUS: obsolete` or delete it.
- Never create two drawers with the same core rule in different phrasings.

Use `mempalace_check_duplicate` as a secondary guard when available.

### 5.4 Freshness Metadata

For entries that may evolve, include a header:

```
STATUS: active
CREATED: YYYY-MM-DD
REVISED: YYYY-MM-DD   (optional)
VERSION: N            (optional)
```

Mark entries as `STATUS: review-needed` when the surrounding codebase has changed significantly but the entry has not been reviewed.

### 5.5 Cross-References

When a project entry depends on shared knowledge, do not copy the shared content. Reference it:

```
[see: ros2/lifecycle] — this component extends the native state machine described there
```

This keeps project entries lean, avoids duplication, and makes the dependency explicit.

---

## 6. Engineering Guardrails

These are operational rules that prevent the memory store from degrading over time:

1. **Do not write to memory without reading first.** Always check for existing entries before creating new ones.
2. **Scope entries correctly.** If knowledge is reusable across projects, it belongs in the shared wing. Resist the temptation to put everything in the project wing for convenience.
3. **Tag types explicitly when ambiguous.** A `[type: anti-pattern]` tag communicates different weight than `[type: project-decision]`.
4. **Do not persist transitive facts.** If a fact is only relevant because of a specific temporary configuration, it will mislead future agents.
5. **Treat obsolescence as maintenance.** When a decision is reversed or a rule is superseded, update or remove the old entry. Stale memory is worse than no memory.
6. **Keep entries atomic.** One entry, one rule. Multi-rule entries are hard to retrieve precisely and hard to update without side effects.

---

## 7. Worked Example: ROS 2 Project

This section illustrates the strategy with a concrete case. **ROS 2 is the example; the pattern generalizes to any multi-project engineering context.**

### Setup

A team is building a robotics system called `lifecore_ros2`. They use MemPalace with two wings:

- `lifecore_ros2` — project wing
- `ros2` — shared wing for general ROS 2 knowledge

### Storing an architecture decision

After deciding that all components must gate message processing on the node's lifecycle activation state, they store:

**Wing:** `lifecore_ros2`  
**Room:** `architecture`  
**Content:**
```
[type: architecture-rule]
STATUS: active
CREATED: 2025-03-01

Topic components must gate all message processing and publication on the node's
activation state. Subscribers must check node state before forwarding messages.
Publishers must only publish when the node is in the ACTIVE state.

Rationale: prevents message processing during partial initialization or cleanup.

[see: ros2/lifecycle] for the state machine this rule extends.
```

The general lifecycle state machine semantics go in the shared wing:

**Wing:** `ros2`  
**Room:** `lifecycle`  
**Content:**
```
[type: transverse-knowledge]
STATUS: active
CREATED: 2025-01-15

ROS 2 lifecycle nodes follow a standard state machine: Unconfigured → Inactive →
Active → Finalized. Transitions are triggered by configure(), activate(), deactivate(),
cleanup(), shutdown(). Do not introduce internal states that shadow or diverge from
this machine.
```

### Retrieving context before a change

A Copilot instruction file specifies:

> Before modifying any component lifecycle code, query `lifecore_ros2` then `ros2`. Merge results. Project rules take precedence only when marked as local overrides.

When an agent is asked to add a new topic component, it queries both wings, finds the gating rule and the lifecycle semantics, and applies both without requiring the developer to explain them again.

### Preventing regression

An anti-pattern that caused a subtle bug gets persisted:

**Wing:** `lifecore_ros2`  
**Room:** `anti-patterns`  
**Content:**
```
[type: anti-pattern]
STATUS: active
CREATED: 2025-03-12

Do not introduce internal boolean flags (e.g., `self._running`) that shadow
the node lifecycle state. This caused a regression where a component processed
messages after deactivation because the internal flag was not reset on cleanup.
Use `self.get_node().get_current_state()` instead.
```

Now every future agent working in this codebase will avoid repeating the same mistake.

---

## 8. Failure Modes and Anti-Patterns

### 8.1 The Dump

**Symptom:** Every session output, debug log, and temporary observation ends up in memory.

**Effect:** Retrieval noise. Agents surface stale, irrelevant, or contradictory entries. The 80% threshold check becomes meaningless because the store is full of near-duplicates.

**Fix:** Write the persistence policy into your instruction file. Only persist after the decision is validated and durable.

---

### 8.2 The Project Island

**Symptom:** All knowledge — including general platform knowledge — is stored in project wings.

**Effect:** Shared knowledge gets replicated across project wings, diverges, and must be maintained in multiple places.

**Fix:** Enforce the scope rule. If a fact belongs in the shared wing, it does not go in the project wing. Use cross-references to link from project entries to shared ones.

---

### 8.3 The Stale Anchor

**Symptom:** Architecture decisions are written once and never updated, even as the codebase evolves.

**Effect:** Agents apply outdated rules. Worse, they apply them confidently because the entry looks authoritative.

**Fix:** Use freshness metadata. Treat a post-refactor sweep of the memory store as a standard engineering task, not optional housekeeping.

---

### 8.4 The Blocker

**Symptom:** An agent or instruction file refuses to proceed when MemPalace is unavailable.

**Effect:** All tasks are blocked by a memory tool outage. Memory becomes a single point of failure.

**Fix:** Always define a fallback chain in your instruction file. MemPalace unavailability should degrade gracefully to local documentation, never block.

---

### 8.5 The Monolith Entry

**Symptom:** A single drawer contains five rules, three rationales, and two cross-references.

**Effect:** The entry is hard to retrieve precisely. A query for one rule returns unrelated content. Updating one rule risks invalidating the others.

**Fix:** One entry, one rule. Split compound entries. Let the room structure provide the grouping.

---

## 9. Minimal Starting Setup

You do not need to implement this strategy fully on day one. A practical starting point:

- **1 project wing** — for the current project
- **1 shared wing** — for reusable platform or framework knowledge
- **2–3 rooms** — `architecture` and `anti-patterns` cover the highest-value content

Avoid over-structuring early. Add rooms only when content justifies them. Refine the scope split only when patterns of mis-scoping emerge. The structure is a tool, not a goal.

---

## 10. Conclusion

MemPalace works well as a flat store for personal notes. It works significantly better as a governed knowledge layer when you apply a small amount of structure:

- **Two wings per project**: one project-scoped, one shared.
- **Standard rooms**: consistent categories that make retrieval predictable.
- **Entry types**: explicit classification that communicates weight.
- **Deduplication discipline**: enrich before you create.
- **Graceful fallback**: memory unavailability is never a blocker.

The effort required is low. Teams can start with a single project wing and one shared wing, using just two or three rooms. The structure can grow incrementally as patterns emerge — there is no need to design the full taxonomy upfront. The payoff — agents that consistently apply the right rules, without being re-explained every session — compounds over time.

This is not the only way to use MemPalace effectively. It is one way that has proven practical in engineering workflows where multiple agents work across multiple projects and need shared, persistent context.

---

*For the standard MemPalace setup and quickstart, see the [README](../README.md).*  
*For VS Code MCP integration details, see [docs/mcp_vscode.md](mcp_vscode.md).*
