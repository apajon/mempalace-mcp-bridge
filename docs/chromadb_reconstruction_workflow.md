# ChromaDB reconstruction workflow reference

## Status

**Classification: experimental.**

This workflow exists to evaluate whether a MemPalace palace created on the stable
ChromaDB `0.6.x` line can be reconstructed into a separate ChromaDB `1.x` target.

It is:

- source-preserving
- validation-first
- deterministic in structure
- useful for advanced evaluation

It is **not**:

- supported bridge functionality
- an in-place migration tool
- an automatic cutover path
- a production guarantee

---

## Problem

This repository intentionally treats ChromaDB `0.6.x` and `1.x` as different lines with
different risk profiles.

The stable bridge path is pinned to `0.6.x` because:

- existing palaces are known to work there
- setup, update, verify, and runtime guards are built around that line
- opening older palaces directly under a `1.x` stack is not a safe assumption

The practical issue is simple:

1. a palace created on the stable `0.6.x` line contains valuable logical drawer data
2. a user may want to test a `1.x` runtime
3. direct reuse of the old palace is not a supported assumption
4. in-place mutation is the wrong safety model for this repo

So the workflow does **not** try to “upgrade the palace in place”.

Instead, it exports logical drawer data from the old palace, rebuilds a separate target,
and validates the result before any human decides whether the target is good enough.

---

## Solution

The workflow uses a **neutral reconstruction bundle**.

The bundle separates source extraction from target rebuild:

1. export logical drawers from the `0.6.x` source palace
2. write them into a small explicit on-disk format
3. import that format into a new target palace
4. validate the rebuilt target against the exported source view

Why this matters:

- the source palace stays untouched
- the target can be disposable
- export and import can run under different runtimes
- validation has a stable reference point

Core bundle contents:

| File | Purpose |
|---|---|
| `reconstruction-export-manifest.json` | source metadata, collection metadata, integrity summary |
| `drawers.jsonl` | one logical drawer per line |
| `reconstruction-retrieval-queries.json` | deterministic retrieval comparison plan |
| `reconstruction-usage-scenarios.json` | deterministic usage comparison plan |

---

## Workflow

## 1. Export from the stable source

The source palace must detect as `chroma_0_6`.

Export is read-only. It extracts:

- drawer ids
- full drawer documents
- logical metadata such as wing, room, file provenance, and chunk index

It also records:

- source format detection
- source integrity summary
- deterministic retrieval queries
- deterministic usage scenarios

Recommended entrypoint:

```bash
./scripts/reconstruct.sh \
  --source-palace ~/.mempalace/palace \
  --target-palace /tmp/palace-target \
  --work-dir /tmp/palace-reconstruction-run \
  --source-python .venv/bin/python \
  --target-python .venv-chromadb1/bin/python
```

The work dir becomes the run record for the reconstruction attempt.

## 2. Import into a separate target

Import requires a **new empty target directory**.

The importer creates a fresh target collection and re-adds the exported logical drawers.

This step is intentionally strict:

- it refuses non-empty target directories
- it refuses malformed bundles
- it refuses unsupported source declarations

The target is not considered trustworthy because import succeeded. Import only means the
target was rebuilt without immediate structural rejection.

## 3. Validate structure and data integrity

Structural validation compares the export bundle against the rebuilt target.

It checks:

- drawer count
- fetched target count vs collection count
- wing/room counts
- exported id set vs target id set
- sample drawer id presence
- target reconstruction manifest presence
- document emptiness
- content length profile
- per-id content hashes
- metadata structure
- metadata key preservation
- metadata value preservation
- embeddings presence when the target API exposes embeddings

## 4. Validate retrieval behavior

Retrieval validation uses the deterministic query plan from the export bundle.

It runs the same queries against source and target, then compares:

- result presence
- anchor-id presence
- result-count drift
- overlap between source and target result ids

This is deliberately stronger than “target returned something” and weaker than “ranking is
identical”. The goal is to detect major semantic divergence without pretending exact ranking
parity is guaranteed.

## 5. Optionally compare usage behavior

Usage comparison runs deterministic multi-step scenarios built from the export bundle.

It classifies each scenario as:

- `acceptable`
- `degraded`
- `unusable`

This gives a user-level signal that is closer to real use than raw retrieval overlap alone.

## 6. Optionally validate MCP runtime

MCP runtime validation launches the experimental MCP server against the rebuilt target and
checks actual tool behavior.

It verifies:

- server startup
- MCP initialize
- tools/list
- required tool availability
- status drawer count
- taxonomy
- search results
- anchor text presence in MCP search responses

This matters because retrieval parity by itself does **not** prove that the rebuilt target
behaves correctly through the MCP interface.

---

## Guarantees

The workflow is designed to guarantee only the following:

1. **Source preservation**
   - the source palace is not mutated by the reconstruction workflow
2. **Separate target**
   - reconstruction happens in a different directory
3. **Deterministic validation inputs**
   - the bundle, retrieval plan, and usage scenarios are explicit artifacts
4. **Explicit checks**
   - structural drift, data-integrity drift, retrieval drift, usage drift, and MCP runtime failure can be detected
5. **Actionable failure surfaces**
   - failures identify the category, the likely cause, where to inspect, and the relevant drawer ids or query ids when available

Those are workflow guarantees.

They are **not** outcome guarantees.

---

## What is validated

The workflow can validate all of the following:

| Area | What is checked |
|---|---|
| Source format | source detects as `chroma_0_6` |
| Source integrity | duplicate ids, blank ids, malformed document rows, duplicate metadata keys |
| Bundle integrity | manifest structure, drawer record structure, retrieval plan, usage plan |
| Target structure | target directory safety, collection creation, target manifest |
| Data integrity | count drift, missing ids, unexpected ids, content hash drift, metadata drift |
| Retrieval | query-plan consistency, anchor presence, overlap, result-count drift |
| Usage | scenario-plan consistency, step-by-step overlap, degraded vs unusable classification |
| MCP runtime | server startup, tool availability, status/taxonomy/search behavior |

This is strong validation.

It is still not the same thing as support.

---

## Limitations

This workflow does **not** guarantee any of the following:

- successful reconstruction for every palace
- identical embeddings
- identical retrieval ranking
- identical user-visible behavior
- support for historical pre-`0.6` palaces
- production readiness of reconstructed `1.x` targets
- automatic cutover
- automatic rollback
- reconstruction of project-side files such as `mempalace.yaml` or `entities.json`
- long-term compatibility with future `1.x` changes

Important consequence:

Passing validation means:

- the target passed the checks that currently exist

It does **not** mean:

- the target is now part of the supported bridge path

---

## When to use this workflow

Use it when you need one of these:

1. **Migration evaluation**
   - you want evidence about whether a specific `0.6.x` palace can be rebuilt under a `1.x` runtime
2. **Runtime testing**
   - you want to compare source and target retrieval behavior in a disciplined way
3. **Experimentation**
   - you want a disposable target for investigation without risking the original palace
4. **Regression analysis**
   - you want explicit artifacts for structure, retrieval, usage, and MCP runtime checks

Good fit:

- maintainers
- advanced users
- anyone comfortable reading validation failures and making a manual go/no-go decision

---

## When not to use it

Do **not** use this workflow when:

1. you need supported bridge behavior today
2. you need automatic migration
3. you cannot keep the original palace intact
4. you cannot tolerate manual review of validation output
5. you are dealing with production-critical data without backup
6. you want a guarantee that a rebuilt `1.x` target is equivalent to the original in all relevant ways

Bad fit:

- normal setup users
- production environments that require support commitments
- critical data paths where a disposable experimental target is not acceptable

---

## Practical guidance

If you use this workflow:

1. keep the original palace unchanged
2. use a new target directory every time
3. keep the full work dir for each run
4. read validation failures before rerunning
5. inspect generated debug artifacts when a comparison fails
6. treat a reconstructed target as experimental even after a clean run

If you do **not** have time to inspect failures carefully, do **not** use this workflow.

---

## Reference commands

Minimal run:

```bash
./scripts/reconstruct.sh \
  --source-palace ~/.mempalace/palace \
  --target-palace /tmp/palace-target \
  --work-dir /tmp/palace-reconstruction-run \
  --source-python .venv/bin/python \
  --target-python .venv-chromadb1/bin/python
```

Broader run with usage and MCP runtime validation:

```bash
./scripts/reconstruct.sh \
  --source-palace ~/.mempalace/palace \
  --target-palace /tmp/palace-target \
  --work-dir /tmp/palace-reconstruction-run \
  --source-python .venv/bin/python \
  --target-python .venv-chromadb1/bin/python \
  --with-usage \
  --with-mcp-runtime
```

Dry-run:

```bash
./scripts/reconstruct.sh \
  --source-palace ~/.mempalace/palace \
  --target-palace /tmp/palace-target \
  --work-dir /tmp/palace-reconstruction-run \
  --source-python .venv/bin/python \
  --target-python .venv-chromadb1/bin/python \
  --dry-run
```

---

## Related documents

- [docs/chromadb_reconstruction_prototype.md](chromadb_reconstruction_prototype.md)
- [docs/chromadb_reconstruction_migration.md](chromadb_reconstruction_migration.md)
- [docs/chromadb_reconstruction_experimental_release.md](chromadb_reconstruction_experimental_release.md)
