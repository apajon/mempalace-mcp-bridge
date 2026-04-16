# Reconstruction migration prototype

## Scope

This is an **exploration-only prototype** for a non-destructive migration flow from a `chroma_0_6` source palace to a separate target palace.

It is **not** stable support and **not** an automatic migration path.

## Prototype design

The prototype is intentionally split into six manual phases:

1. **Export**
   - validate source format with the detector
   - require `chroma_0_6`
   - extract logical drawers from SQLite into a neutral export bundle

2. **Import**
   - require a separate, empty target directory
   - rebuild a fresh target collection from the export bundle
   - write a target reconstruction manifest

3. **Validate**
   - compare exported drawer count vs imported count
   - compare full exported id set vs target id set
   - compare wing/room counts
   - compare per-id content hashes and length profile
   - compare per-id metadata keys and values
   - verify sample drawer ids exist
   - verify the target reconstruction manifest exists
   - optionally verify embeddings are present when the target API exposes them

4. **Validate retrieval**
   - generate a deterministic query plan from the export bundle
   - run the same query plan on the source palace and reconstructed target
   - compare result presence, anchor-id presence, overlap, and result-count drift
   - tolerate ranking differences while still detecting major semantic divergence

5. **Compare usage behavior**
   - generate a deterministic set of user-level usage scenarios from the export bundle
   - run the same scenarios on the source palace and reconstructed target
   - compare step-by-step result presence, anchor retrieval, overlap, and drift
   - classify the target as `acceptable`, `degraded`, or `unusable`

6. **Validate MCP runtime**
   - launch the MCP server against the reconstructed palace
   - perform a real MCP initialize → tools/list → tools/call flow
   - verify status/taxonomy/search behavior through the MCP interface
   - detect runtime crashes, empty responses, and backend/tool mismatches

The prototype never mutates the source palace and never performs a cutover.

## Files

- `scripts/palace_reconstruction_prototype.py`
- `tests/test_palace_reconstruction_prototype.py`

## Safety assumptions

- source palace must detect as `chroma_0_6`
- source export is read-only and uses raw SQLite extraction
- target palace must be a new empty directory
- the operator chooses the target runtime explicitly
- validation must pass before any manual switch

## Explicit limitations

- no in-place migration
- no automatic cutover
- no rollback automation beyond “keep the original source untouched”
- no guarantee yet that rebuilt search quality is equivalent
- no guarantee yet for historical pre-`0.6` palaces
- no reconstruction of project-side files like `mempalace.yaml` or `entities.json`

## Neutral bundle format spec

The neutral reconstruction bundle is now an explicit on-disk format. It is intentionally small,
JSON-based, and easy to inspect by hand.

### Bundle layout

At the bundle root:

| Path | Required | Purpose |
|---|---|---|
| `reconstruction-export-manifest.json` | yes | Declares bundle type, file layout, source context, collection settings, and integrity summary |
| `drawers.jsonl` | yes | One JSON object per exported drawer |
| `reconstruction-retrieval-queries.json` | optional | Deterministic retrieval query plan used for source/target comparison |
| `reconstruction-usage-scenarios.json` | optional | Deterministic user-level usage scenarios used for source/target comparison |

`reconstruction-retrieval-queries.json` is optional only for older prototype bundles created
before retrieval validation existed. New exports always include it.

`reconstruction-usage-scenarios.json` is optional only for older prototype bundles created
before usage comparison existed. New exports always include it.

### Manifest structure

Required top-level fields:

- `format_version` — positive integer
- `bundle_type` — must be `mempalace_reconstruction_bundle`
- `created_at` — UTC timestamp string
- `files` — object containing bundle-relative file names
- `collection` — collection definition for reconstruction
- `source` — source palace metadata
- `summary` — deterministic export summary

Optional top-level fields:

- `warnings` — informational warnings
- `retrieval_validation` — retrieval-plan metadata
- `usage_validation` — usage-scenario metadata

#### `files`

Required fields:

- `drawers`
- `retrieval_queries`
- `usage_scenarios`

Both must be safe relative paths inside the bundle.

#### `collection`

Required fields:

- `name`

Optional fields:

- `metadata`

Current export writes:

```json
{
  "name": "mempalace_drawers",
  "metadata": {
    "hnsw:space": "cosine"
  }
}
```

#### `source`

Required fields:

- `palace_path`
- `sqlite_path`
- `detected_format`
- `detection_confidence`

Optional fields:

- `detection_evidence`
- `chromadb_version`
- `mempalace_version`
- `integrity`

#### `summary`

Required fields:

- `drawer_count`
- `sample_ids`
- `metadata_keys`
- `wing_room_counts`

Optional fields:

- `id_integrity`
- `content_integrity`
- `metadata_integrity`

#### `retrieval_validation`

Optional for backward compatibility, but required on new exports.

Fields:

- `queries_file`
- `query_count`
- `top_k`

#### `usage_validation`

Optional for backward compatibility, but required on new exports.

Fields:

- `scenarios_file`
- `scenario_count`
- `top_k`

### Drawer record format (`drawers.jsonl`)

Each non-empty line must be a JSON object with exactly these fields:

- `id` — required string
- `document` — required string
- `metadata` — required object

`metadata` may be empty. Its values are limited to simple JSON scalars preserved by the current
export path:

- string
- integer
- float
- boolean

### Bundle invariants

- drawer ids must be unique
- drawer ids must be non-empty
- `document` must be non-empty text
- `metadata` must remain object-shaped
- `summary.drawer_count` must match the number of drawer records
- `summary.sample_ids` and `summary.wing_room_counts` must match bundle contents
- `collection.name` must match the reconstructed collection used by this prototype
- when present, the retrieval query file must match the manifest declaration
- when present, the usage scenario file must match the manifest declaration

### Compatibility

- new exports always write the explicit manifest fields above
- import keeps a small legacy fallback for older prototype bundles that lack:
  - `bundle_type`
  - `files`
  - `collection`
  - `retrieval_validation`
  - `usage_validation`
- malformed bundles are rejected early instead of being interpreted loosely

### Example manifest

```json
{
  "format_version": 1,
  "bundle_type": "mempalace_reconstruction_bundle",
  "created_at": "2026-04-16T10:40:07Z",
  "files": {
    "drawers": "drawers.jsonl",
    "retrieval_queries": "reconstruction-retrieval-queries.json",
    "usage_scenarios": "reconstruction-usage-scenarios.json"
  },
  "collection": {
    "name": "mempalace_drawers",
    "metadata": {
      "hnsw:space": "cosine"
    }
  },
  "source": {
    "palace_path": "/home/user/.mempalace/palace",
    "sqlite_path": "/home/user/.mempalace/palace/chroma.sqlite3",
    "detected_format": "chroma_0_6",
    "detection_confidence": "high"
  },
  "summary": {
    "drawer_count": 2,
    "sample_ids": ["drawer_a", "drawer_b"],
    "metadata_keys": ["chunk_index", "room", "wing"],
    "wing_room_counts": {
      "proj": {
        "code": 1,
        "docs": 1
      }
    }
  },
  "retrieval_validation": {
    "queries_file": "reconstruction-retrieval-queries.json",
    "query_count": 2,
    "top_k": 5
  },
  "usage_validation": {
    "scenarios_file": "reconstruction-usage-scenarios.json",
    "scenario_count": 3,
    "top_k": 5
  }
}
```

### Example `drawers.jsonl` entries

```json
{"document":"alpha text","id":"drawer_a","metadata":{"chunk_index":0,"room":"docs","wing":"proj"}}
{"document":"beta text","id":"drawer_b","metadata":{"chunk_index":1,"room":"code","wing":"proj"}}
```

### Example retrieval query plan

```json
{
  "format_version": 1,
  "created_at": "2026-04-16T10:40:07Z",
  "top_k": 5,
  "queries": [
    {
      "query_id": "query-001",
      "query_text": "alpha text",
      "anchor_id": "drawer_a",
      "wing": "proj",
      "room": "docs",
      "document_preview": "alpha text",
      "selection_reason": "wing_room_representative"
    }
  ]
}
```

### Example usage scenario plan

```json
{
  "format_version": 1,
  "created_at": "2026-04-16T10:40:07Z",
  "top_k": 5,
  "scenarios": [
    {
      "scenario_id": "usage-001",
      "scenario_type": "simple_query",
      "anchor_id": "drawer_a",
      "wing": "proj",
      "room": "docs",
      "steps": [
        {
          "step_id": "step-001",
          "query_text": "alpha text",
          "purpose": "simple_lookup"
        }
      ]
    },
    {
      "scenario_id": "usage-003",
      "scenario_type": "multi_step_retrieval",
      "anchor_id": "drawer_a",
      "wing": "proj",
      "room": "docs",
      "steps": [
        {
          "step_id": "step-001",
          "query_text": "alpha",
          "purpose": "initial_lookup"
        },
        {
          "step_id": "step-002",
          "query_text": "alpha text",
          "purpose": "refined_lookup"
        }
      ]
    },
    {
      "scenario_id": "usage-005",
      "scenario_type": "copilot_prompt",
      "anchor_id": "drawer_b",
      "wing": "proj",
      "room": "code",
      "steps": [
        {
          "step_id": "step-001",
          "query_text": "I need context about beta text. Focus on wing proj room code.",
          "purpose": "copilot_style_lookup"
        }
      ]
    }
  ]
}
```

## Commands

### 1. Export from a stable source

Run this under the source-safe environment:

```bash
python3 scripts/palace_reconstruction_prototype.py export \
  --source-palace ~/.mempalace/palace \
  --output-dir /tmp/palace-export
```

Artifacts produced:

- `/tmp/palace-export/reconstruction-export-manifest.json`
- `/tmp/palace-export/drawers.jsonl`
- `/tmp/palace-export/reconstruction-retrieval-queries.json`
- `/tmp/palace-export/reconstruction-usage-scenarios.json`

### 2. Import into a separate target

Run this under the target runtime you want to evaluate:

```bash
python3 scripts/palace_reconstruction_prototype.py import \
  --export-dir /tmp/palace-export \
  --target-palace /tmp/palace-target
```

Artifact produced in the target:

- `/tmp/palace-target/reconstruction-target-manifest.json`

### 3. Validate the rebuilt target

```bash
python3 scripts/palace_reconstruction_prototype.py validate \
  --export-dir /tmp/palace-export \
  --target-palace /tmp/palace-target
```

### 4. Record retrieval results in the source-safe environment

```bash
python3 scripts/palace_reconstruction_prototype.py record-retrieval \
  --palace ~/.mempalace/palace \
  --queries-file /tmp/palace-export/reconstruction-retrieval-queries.json \
  --output /tmp/palace-export/source-retrieval-results.json \
  --label source
```

### 5. Record retrieval results in the target environment

```bash
python3 scripts/palace_reconstruction_prototype.py record-retrieval \
  --palace /tmp/palace-target \
  --queries-file /tmp/palace-export/reconstruction-retrieval-queries.json \
  --output /tmp/palace-export/target-retrieval-results.json \
  --label target
```

### 6. Compare source vs target retrieval

```bash
python3 scripts/palace_reconstruction_prototype.py compare-retrieval \
  --source-results /tmp/palace-export/source-retrieval-results.json \
  --target-results /tmp/palace-export/target-retrieval-results.json
```

### 7. Record usage scenarios in the source-safe environment

```bash
python3 scripts/palace_reconstruction_prototype.py record-usage \
  --palace ~/.mempalace/palace \
  --scenarios-file /tmp/palace-export/reconstruction-usage-scenarios.json \
  --output /tmp/palace-export/source-usage-results.json \
  --label source
```

### 8. Record usage scenarios in the target environment

```bash
python3 scripts/palace_reconstruction_prototype.py record-usage \
  --palace /tmp/palace-target \
  --scenarios-file /tmp/palace-export/reconstruction-usage-scenarios.json \
  --output /tmp/palace-export/target-usage-results.json \
  --label target
```

### 9. Compare source vs target usage behavior

```bash
python3 scripts/palace_reconstruction_prototype.py compare-usage \
  --source-results /tmp/palace-export/source-usage-results.json \
  --target-results /tmp/palace-export/target-usage-results.json
```

### 10. Validate MCP runtime against the reconstructed target

Run this in the target environment you want to evaluate. The stable launcher is intentionally left
alone; this command defaults to the exploration launcher so the runtime can be probed without
changing `.mcp.json` or the stable branch behavior.

```bash
/path/to/target-python scripts/palace_reconstruction_prototype.py validate-mcp-runtime \
  --export-dir /tmp/palace-export \
  --palace /tmp/palace-target \
  --python /path/to/target-python \
  --launcher-script scripts/run_mcp_server_exploration.py
```

Example with the side-by-side exploration environment from this branch:

```bash
.venv-chromadb1/bin/python scripts/palace_reconstruction_prototype.py validate-mcp-runtime \
  --export-dir /tmp/palace-export \
  --palace /tmp/palace-target \
  --python .venv-chromadb1/bin/python
```

## Validation procedure

Minimum validation for the prototype:

1. export succeeds without modifying the source palace
2. import succeeds into a separate target path
3. validation reports:
   - `drawer_count_matches`
   - `fetched_drawer_count_matches_collection`
   - `wing_room_counts_match`
   - `export_ids_unique`
   - `target_ids_unique`
   - `id_sets_match`
   - `documents_non_empty`
   - `content_length_profile_matches`
   - `content_hashes_match`
   - `metadata_structures_valid`
   - `metadata_keys_preserved`
   - `metadata_values_match`
    - `sample_ids_present`
    - `target_manifest_present`
    - `embeddings_present` when accessible
4. retrieval validation reports:
   - `query_plan_matches`
   - `source_results_present`
   - `source_anchor_ids_present`
   - `target_results_present`
   - `target_anchor_ids_present`
   - `result_counts_within_tolerance`
   - `id_overlap_meets_threshold`
5. usage comparison reports:
   - `scenario_plan_matches`
   - `source_results_present`
   - `source_anchor_ids_present`
   - `target_results_present`
   - `target_anchor_ids_present`
   - `result_counts_within_tolerance`
   - `id_overlap_meets_threshold`
   - recommendation: `acceptable`, `degraded`, or `unusable`
6. MCP runtime validation reports:
    - `server_started`
    - `initialize_succeeded`
    - `tools_listed`
    - `required_tools_available`
   - `status_matches_drawer_count`
   - `status_reports_target_palace`
    - `taxonomy_matches_export`
    - `search_results_present`
    - `anchor_texts_present`
    - `server_stable_during_queries`
7. manual target-side checks still recommended:
    - verify MCP startup in the target environment

## What the stronger validation now checks

### ID integrity

- source-side export refuses:
  - blank ids
  - duplicate ids in SQLite
  - export count drift vs raw `embeddings` rows
- target-side validation checks:
  - fetched target count matches collection count
  - full target id set matches the export bundle exactly
  - no missing ids
  - no unexpected ids

### Content integrity

- export/import/validate require non-empty text payloads
- validation compares:
  - full per-id content hashes
  - deterministic length profile:
    - total chars
    - min chars
    - max chars
    - fixed size buckets (`0`, `1-31`, `32-127`, `128-511`, `512+`)

### Metadata integrity

- source-side export refuses duplicate metadata keys per SQLite drawer row
- validation checks:
  - metadata remains object-shaped
  - metadata keys present in export are still present in target
  - canonicalized metadata values match per id

### Embeddings

- validation tries to fetch embeddings from the target collection
- if the runtime exposes them, missing embeddings fail validation
- if the runtime does not expose them, the check is reported as skipped rather than guessed

## Retrieval validation design

### Query selection

- export now writes `reconstruction-retrieval-queries.json`
- queries are generated deterministically from exported drawers:
  - sort drawers by taxonomy and id
  - pick one query per wing/room where possible
  - fill remaining slots by id order
  - derive each query from the leading normalized document snippet
- each query keeps an **anchor id**: the drawer that the query came from

This keeps the query set:

- deterministic
- explainable
- tied to real stored content
- representative across rooms when possible

### Comparison model

For each query, the comparison checks:

- did the source return any results?
- did the source return the anchor id?
- did the target return any results?
- did the target return the anchor id?
- is the result-count difference within tolerance?
- does the target overlap enough with the source result ids?

Defaults:

- `top_k = 5`
- `count_tolerance = 1`
- `min_overlap_ratio = 0.4`

The overlap ratio is computed against the **source** result set, not the ranking order. This
allows embedding/ranking differences while still catching a target that no longer retrieves
substantially the same content.

## Usage comparison design

### Scenario selection

New exports also write `reconstruction-usage-scenarios.json`.

The scenario set is deterministic and intentionally small:

- **simple query** — direct lookup using the exported text snippet
- **multi-step retrieval** — a broad query followed by a refined query for the same anchor
- **Copilot-style prompt** — a short natural-language request that mentions the anchor topic and, when available, wing/room context

Scenario anchors are selected from the same stable drawer ordering used by retrieval validation:

- sort by wing, room, and id
- take up to two representative anchors for simple lookups
- reuse the earliest representatives for multi-step refinement
- generate one Copilot-style prompt from a later representative when possible

### Comparison model

For each scenario step, the comparison checks:

- did the source return results?
- did the source retrieve the anchor id?
- did the target return results?
- did the target retrieve the anchor id?
- is the result-count difference within tolerance?
- does the target retain enough id overlap with the source results?

Defaults:

- `top_k = 5`
- `count_tolerance = 1`
- `min_overlap_ratio = 0.4`

### Recommendation rules

Per scenario:

- **acceptable** — target keeps the anchor, result counts stay close, and overlap meets threshold
- **degraded** — target still returns something useful, but anchor retrieval, counts, or overlap drift noticeably
- **unusable** — target drops to zero results for a source-positive step, or the overlap collapses completely

If a prompt shape is weak enough that the **source** also misses its own anchor, that is reported as
a source-baseline caveat instead of automatically counting as target degradation.

Overall recommendation:

- **acceptable** — all scenarios are acceptable
- **degraded** — at least one scenario is degraded and none are unusable
- **unusable** — any scenario is unusable or the scenario plans do not match

## MCP runtime validation design

### Why this exists

Structural and retrieval checks still do not prove that the reconstructed palace works when the
actual MCP server is launched under the target runtime. The MCP runtime validator closes that gap
by probing the real stdio server process.

### Flow

The command:

1. loads the export bundle and deterministic retrieval query plan
2. launches the chosen MCP server script with `MEMPALACE_PALACE_PATH` pointing at the target palace
3. performs:
   - `initialize`
   - `notifications/initialized`
   - `tools/list`
   - `tools/call` for:
     - `mempalace_status`
     - `mempalace_get_taxonomy`
     - `mempalace_search`
4. compares runtime responses to bundle expectations

### What it checks

- the server process starts and stays alive long enough to answer requests
- MCP handshake succeeds
- required tools are actually exposed
- `mempalace_status` reports the expected drawer count and target palace path
- `mempalace_get_taxonomy` matches the exported taxonomy
- each deterministic search query returns results through MCP
- each query still retrieves the anchor document text somewhere in the MCP response set

### Why anchor text instead of id

`mempalace_search` returns result text, taxonomy metadata, and similarity — not drawer ids. So the
runtime validator uses the exported anchor document text as the deterministic check that the
expected content is still retrievable through MCP.

## Example validation output

Passing validation:

```text
[OK]    Reconstruction validation passed
[OK]    drawer_count_matches
[OK]    fetched_drawer_count_matches_collection
[OK]    wing_room_counts_match
[OK]    export_ids_unique
[OK]    target_ids_unique
[OK]    id_sets_match
[OK]    documents_non_empty
[OK]    content_length_profile_matches
[OK]    content_hashes_match
[OK]    metadata_structures_valid
[OK]    metadata_keys_preserved
[OK]    metadata_values_match
[OK]    sample_ids_present
[OK]    target_manifest_present
[OK]    embeddings_present
[INFO]  Drawer counts: expected=2 actual=2
[INFO]  Content chars: expected_total=19 actual_total=19
[INFO]  Embeddings present: 2/2
```

Failing validation:

```text
[ERROR] Reconstruction validation failed
[FAIL]  id_sets_match
[FAIL]  content_hashes_match
[FAIL]  metadata_keys_preserved
[FAIL]  metadata_values_match
[INFO]  Missing ids: drawer_b
[INFO]  Unexpected ids: drawer_extra
[INFO]  Content mismatches: drawer_a
[INFO]  Metadata keys missing in target: drawer_a
```

Passing retrieval comparison:

```text
[OK]    Retrieval validation passed
[OK]    query_plan_matches
[OK]    source_results_present
[OK]    source_anchor_ids_present
[OK]    target_results_present
[OK]    target_anchor_ids_present
[OK]    result_counts_within_tolerance
[OK]    id_overlap_meets_threshold
[INFO]  Query comparison: 3 queries, count_tolerance=1, min_overlap_ratio=0.4
```

Failing retrieval comparison:

```text
[ERROR] Retrieval validation failed
[FAIL]  target_anchor_ids_present
[FAIL]  id_overlap_meets_threshold
[INFO]  Query comparison: 3 queries, count_tolerance=1, min_overlap_ratio=0.4
[INFO]  query-001 overlap=0 source_count=3 target_count=3
[INFO]  query-001 mismatches: target did not retrieve anchor id, source overlap ratio 0.0 is below threshold 0.4
```

Passing usage comparison:

```text
[OK]    Usage comparison passed
[OK]    scenario_plan_matches
[OK]    source_results_present
[OK]    source_anchor_ids_present
[OK]    target_results_present
[OK]    target_anchor_ids_present
[OK]    result_counts_within_tolerance
[OK]    id_overlap_meets_threshold
[INFO]  Usage recommendation: acceptable (acceptable=5 degraded=0 unusable=0)
```

Failing usage comparison:

```text
[ERROR] Usage comparison detected divergence
[FAIL]  target_anchor_ids_present
[FAIL]  id_overlap_meets_threshold
[INFO]  Usage recommendation: unusable (acceptable=0 degraded=0 unusable=5)
[INFO]  usage-001 step-001 mismatches: target did not retrieve anchor id, source overlap ratio 0.0 is below threshold 0.4
```

Passing MCP runtime validation:

```text
[OK]    MCP runtime validation passed
[OK]    server_started
[OK]    initialize_succeeded
[OK]    tools_listed
[OK]    required_tools_available
[OK]    status_matches_drawer_count
[OK]    status_reports_target_palace
[OK]    taxonomy_matches_export
[OK]    search_results_present
[OK]    anchor_texts_present
[OK]    server_stable_during_queries
[INFO]  Launcher: /path/to/python /repo/scripts/run_mcp_server_exploration.py
[INFO]  Palace: /tmp/palace-target
```

Failing MCP runtime validation:

```text
[ERROR] MCP runtime validation failed
[FAIL]  taxonomy_matches_export
[FAIL]  anchor_texts_present
[INFO]  query-001 result_count=3 anchor_text_present=False
[INFO]  query-001 mismatches: anchor text not present in MCP search results
```

## Interpretation guidelines

### Acceptable

- every query returns results on both source and target
- the anchor id is still present on the target for every query
- target result counts stay within the configured tolerance
- overlap is partial but stays above the threshold

This means the reconstruction is not identical in ranking, but it still appears usable.

### Suspicious

- one query drops below the overlap threshold
- one query loses the anchor id but others remain healthy
- count drift is repeated but small

This suggests semantic drift that should be reviewed manually before trusting the target.

### Usage degraded

- one or more usage scenarios still return relevant results but lose the anchor intermittently
- refined follow-up steps still work, but overlap or counts drift beyond tolerance
- Copilot-style prompts return related content without matching the source anchor set reliably

This means the target may still be useful for exploration, but not yet close enough to trust as a replacement.

### Usage unusable

- target usage scenarios return no results where the source succeeds
- anchor ids disappear across multiple scenarios
- overlap collapses across the scenario set, especially on refined follow-up steps

This means the target does not preserve practical search behavior well enough for normal use.

### Failure

- target returns no results for source queries that worked
- anchor ids disappear repeatedly
- overlap collapses to zero or near-zero across multiple queries
- query plans or result bundles do not match

This means the reconstructed palace should not be treated as a usable replacement yet.

### MCP runtime failure

- the server exits during initialize or tool calls
- `tools/list` does not expose the expected MemPalace tools
- `mempalace_status` or `mempalace_get_taxonomy` disagree with the bundle
- search works structurally but the anchor texts are no longer retrievable through MCP

This means the reconstructed palace may exist on disk but is not yet a trustworthy MCP backend.

## Risk notes

- the source export depends on SQLite-level assumptions about MemPalace drawer storage
- the target import depends on the currently installed ChromaDB runtime in the environment that runs `import`
- retrieval validation tolerates ranking differences; it is intended to detect major semantic drift, not prove identical ranking
- usage comparison is a deterministic usability proxy, not a replay of full Copilot conversations
- MCP runtime validation intentionally uses the exploration launcher by default so stable `.mcp.json` behavior is not modified
- this prototype should be abandoned immediately if counts drift or target behavior is unstable

## Remaining limitations

- validation proves id/content/metadata preservation against the export bundle, not end-user search parity
- source-side id loss can only be proven for bundles exported with this strengthened exporter; older bundles may lack the added source integrity summary
- metadata checking is intentionally shape-preserving, not schema-enforcing beyond the fields that actually exist in the export
- embedding validation only runs when the target runtime exposes embeddings through `collection.get(..., include=["embeddings"])`
- retrieval validation depends on the source runtime still being able to query the source palace normally
- usage comparison depends on both environments being able to query the relevant collection directly
- deterministic query generation is content-based and intentionally simple; it does not try to measure broad search quality beyond anchored representative queries
- MCP runtime validation depends on the target Python environment being able to import and run `mempalace.mcp_server`

## Recommendation

**Good enough to continue experimentally, not good enough to support.**

The prototype is useful as a narrow lab workflow because it is:

- non-destructive
- source-preserving
- explicit about target path separation
- validation-first

But it still needs stronger validation before anyone should trust it for real migration decisions.
