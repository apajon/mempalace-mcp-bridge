# ChromaDB reconstruction migration assessment

## Status

**Recommendation: experimental only.**

A reconstruction-style migration from the stable `0.6.x` line to a `1.x` line appears **feasible in principle**, but it is **not yet trustworthy enough to claim support**.

Official positioning in this repository should be:

- **experimental**
- **unsupported as a normal user workflow**
- **source-preserving and validation-first**
- **not a supported upgrade path**

The current evidence says:

- a copied bridge-created `0.6.3` palace was readable under `chromadb==1.5.7` in the exploration environment
- MemPalace already stores enough logical drawer data to rebuild a collection elsewhere
- upstream MemPalace `3.3.0` includes a `migrate` command that uses raw SQLite extraction plus rebuild

But there are still important blockers:

- the upstream migrate command is **in-place / swap-based**, not source-preserving
- its source-version detection heuristic is **already wrong on our sampled `0.6.3` palace**
- this repo has **no neutral export/import format** yet
- validation rules for search-quality parity and historical palace edge cases are still unproven

So the direction looks viable, but **official migration support should wait**.

---

## Scope

This assessment is about **reconstruction migration**, not in-place mutation:

1. export logical drawer data from the source palace
2. build a separate target palace under the target stack
3. validate
4. switch only after validation
5. preserve the original source untouched for rollback

This is intentionally different from “open the old palace with the new stack and let it mutate.”

---

## Confirmed capabilities

### 1. The stable palace already contains logical drawer data, not only vectors

Confirmed from the installed MemPalace `3.1.0` miner and live palace inspection:

- drawers are stored with:
  - `id`
  - full `document` text
  - metadata:
    - `wing`
    - `room`
    - `source_file`
    - `chunk_index`
    - `added_by`
    - `filed_at`
    - sometimes `source_mtime`

That means a rebuild does **not** have to depend on the original project files being available.

### 2. MemPalace already has a collection-rebuild primitive

Confirmed in `mempalace 3.1.0` and `3.3.0`:

- `mempalace repair` reads all drawer ids/documents/metadatas
- rebuilds the collection by re-adding them

This is **not** a migration workflow by itself, but it proves the logical reconstruction model is already used upstream.

### 3. Upstream `mempalace 3.3.0` already has a raw-SQL extraction path

Confirmed from `mempalace 3.3.0`:

- `mempalace migrate` includes `extract_drawers_from_sqlite(db_path)`
- it reads drawer ids, documents, and metadata directly from `chroma.sqlite3`
- it bypasses ChromaDB’s API when the database is not readable under the current runtime

This is the most important upstream building block for version-line reconstruction.

### 4. The current `0.6.3` palace schema already contains enough SQL-level data for extraction

Confirmed from direct SQLite inspection of the stable palace:

- `embeddings.embedding_id` stores drawer ids
- `embedding_metadata` stores:
  - `chroma:document`
  - logical metadata fields like `wing`, `room`, `source_file`, `chunk_index`

So a neutral export can be produced from SQLite without opening the palace through ChromaDB.

---

## Confirmed limitations and risks

### 1. There is no reusable export/import command in this repo yet

The bridge currently has:

- setup/update/verify
- format detection
- safety gating

It does **not** have:

- `export` command
- `import` command
- `validate-migration` command
- target-path switch helper

### 2. Upstream `migrate` does not follow the preferred rollback model

Observed in `mempalace 3.3.0`:

- it backs up the source
- creates a temporary rebuilt palace
- then **deletes the original palace path and swaps the rebuilt one into place**

That is safer than blind mutation, but it is still an **in-place destination swap**, not a clean “leave source intact, create separate target, switch later” workflow.

### 3. Upstream source-version detection is not trustworthy enough

Observed on a copied bridge-created `0.6.3` palace:

```text
Source: ChromaDB 1.x
Target: ChromaDB 1.5.7
Palace is already readable by chromadb 1.5.7.
```

But direct SQLite inspection of the real stable palace showed:

- the stable `0.6.3` palace already has `schema_str` in `collections`

Upstream `detect_chromadb_version()` currently treats the presence of `schema_str` as `1.x`, which is **incorrect for our sampled `0.6.3` palace**.

That means any migration design must **not trust that heuristic**.

### 4. A rebuilt target palace would preserve drawer content, but not all workspace artifacts

The palace stores logical drawer data, not the full source workspace setup.

Not reliably reconstructible from palace storage alone:

- `mempalace.yaml`
- `entities.json`
- room descriptions from the original project config
- any external source tree state no longer present in drawer metadata

For retrieval/search, this may be acceptable. For full project reconstitution, it is not.

### 5. Search parity after rebuild is still an assumption

A rebuilt palace may preserve:

- drawer ids
- drawer documents
- logical metadata

But it may still differ in:

- embedding generation details
- ranking behavior
- search distance distribution
- tokenization / index configuration behavior

This needs explicit validation, not assumption.

---

## Upstream reusable primitives

### Confirmed upstream primitives

| Primitive | Where | Usefulness |
|---|---|---|
| Read logical drawers through API | `mempalace repair` | useful when source is readable under its own stack |
| Read logical drawers from raw SQLite | `mempalace 3.3.0 migrate` | useful for version-mismatched source |
| Rebuild collection from ids/docs/metadatas | `mempalace repair` / `migrate` | core target reconstruction primitive |

### Missing or insufficient upstream pieces

| Gap | Why it matters |
|---|---|
| No stable neutral export artifact | hard to separate source export from target import cleanly |
| In-place/swap migration model | conflicts with source-preserving rollback philosophy |
| Weak source-version detection heuristic | unsafe for routing migration flows |
| No formal post-migration validator | impossible to claim reliability |

---

## What can be exported logically today

### Confirmed exportable payload

A source-side exporter can extract at least:

- drawer `id`
- drawer `document`
- drawer metadata:
  - `wing`
  - `room`
  - `source_file`
  - `chunk_index`
  - `added_by`
  - `filed_at`
  - `source_mtime` when present

This is enough to reconstruct:

- the `mempalace_drawers` collection
- wing/room taxonomy
- file-level provenance references

### Not confirmed exportable as first-class structured data

- original room descriptions from `mempalace.yaml`
- entity detection config from `entities.json`
- any non-drawer collections or future Chroma metadata semantics not used by MemPalace search

---

## Proposed migration flow

## Phase 0 — preconditions

1. Detect the source palace format using the current detector.
2. Only allow reconstruction planning when the source is explicitly detected as `chroma_0_6`.
3. Refuse `unknown` sources.
4. Refuse in-place migration targets.

## Phase 1 — source export (old stack)

Run under the source-safe environment (`mempalace 3.1.0` + `chromadb 0.6.x`):

1. Open the source palace **read-only** or extract from raw SQLite.
2. Export a neutral artifact, ideally:
   - `drawers.jsonl` or chunked JSONL files
   - one record per drawer:
     - `id`
     - `document`
     - `metadata`
3. Export a manifest alongside it:
   - source palace path
   - source detected format
   - source package versions
   - drawer count
   - wing/room counts
   - export timestamp

This phase must not mutate the source palace.

## Phase 2 — target build (new stack)

Run under the target-safe environment (`mempalace 3.3.0` + `chromadb 1.x`):

1. Create a brand-new target palace in a separate directory.
2. Create a fresh `mempalace_drawers` collection.
3. Import exported drawers in batches.
4. Write a target manifest that clearly marks:
   - it is a rebuilt target
   - source export metadata
   - target package versions

## Phase 3 — validation

Validate **before any switch**:

1. exported drawer count == imported drawer count
2. wing/room distribution matches
3. sample drawer ids exist in target
4. sample metadata fields survive import
5. target `search` works on known queries
6. MCP startup under target stack works
7. target remains isolated from the source path

## Phase 4 — controlled switch

Do **not** overwrite the source palace.

Instead:

1. keep source palace intact
2. point configuration to the target palace explicitly
3. only after successful acceptance testing, make the target the active one

Rollback is then simple:

- point back to the original source palace
- discard the rebuilt target if needed

---

## Required building blocks for this repo

To make this reconstruction workflow credible, the repo would need:

1. **Source export command**
   - source-safe
   - no mutation
   - outputs neutral artifact + export manifest

2. **Target import command**
   - target-safe
   - creates a new palace path only
   - no source overwrite

3. **Migration plan/validation command**
   - compares counts and taxonomy
   - records pass/fail checks

4. **Target manifest/schema extension**
   - records reconstructed-from metadata
   - records source export summary

5. **Safer version/source routing**
   - do not trust naive structural version heuristics
   - keep detector + safety gate as the first decision layer

---

## Validation checklist

Before claiming any migration support, all of the following should be demonstrated:

### Source-side validation

- detector classifies source as `chroma_0_6`
- source export completes without mutating source
- export manifest count matches actual exported records

### Target-side validation

- target palace is created in a separate path
- import count matches export count
- all required metadata keys survive import
- target manifest is written

### Functional validation

- sample `search` queries return expected source files/topics
- MCP server starts on the target stack
- `status` / taxonomy counts match source export summary

### Safety validation

- failed import does not affect source palace
- target can be deleted independently
- rollback is only a path/config switch

### Coverage gaps still needing proof

- very old pre-`0.6` palaces
- mixed/partially repaired palaces
- large palaces and long-running batch imports
- compressed/advanced MemPalace features beyond basic drawers

---

## What cannot yet be trusted

Do **not** trust these yet:

1. upstream source-version detection in `mempalace migrate`
2. search-quality equivalence after rebuild
3. migration behavior on historical pre-`0.6` palaces
4. in-place swap workflows as a safe default

---

## Final assessment

**Feasible, but not yet supportable.**

The safest path is a **two-environment, source-preserving reconstruction flow**:

- export from old source
- build new target separately
- validate thoroughly
- switch by configuration only after success

That direction is technically plausible with the current upstream and repo building blocks, but the current evidence is **not strong enough to claim migration support**.

So the right recommendation today is:

**Keep official migration support deferred, but continue the reconstruction workflow only as an experimental prototype that remains explicitly non-destructive and validation-first.**

That means:

- document it openly
- keep warnings prominent
- avoid claiming ChromaDB `1.x` support for the bridge itself
- limit the intended audience to maintainers and advanced evaluators
