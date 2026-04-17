# Migration Robustness Matrix

Generated: 2026-04-17T19:07:37Z

## Summary

| Metric | Count |
|--------|-------|
| Total cases | 19 |
| Full success | 7 |
| Degraded | 0 |
| Partial failure | 12 |
| Hard failure | 0 |

## Outcome Legend

| Outcome | Meaning |
|---------|---------|
| `full_success` | Export + import + validation all pass cleanly |
| `degraded` | Pipeline completes but with warnings or validation quirks |
| `partial_failure` | Pipeline rejects input with clear, diagnosable error |
| `hard_failure` | Unhandled exception or silent data corruption |

## Root Cause Classes

| Class | Meaning |
|-------|---------|
| `expected_limitation` | Pipeline correctly rejects unsupported input |
| `fixable_bug` | Pipeline should handle this better |
| `upstream_constraint` | ChromaDB or mempalace limitation beyond our control |

## Detailed Results

| Case | Defect | Drawers | Outcome | Stage Failed | Root Cause | Detail |
|------|--------|---------|---------|-------------|------------|--------|
| `valid_baseline` | none (control) | 3 | ✅ `full_success` | — | `—` | all stages passed cleanly |
| `missing_metadata` | missing wing/room/all metadata fields | 5 | 🚫 `partial_failure` | import | `expected_limitation` | import rejected: target runtime rejected a batch during import |
| `inconsistent_wing_room` | empty/special/long wing/room names | 6 | ✅ `full_success` | — | `—` | all stages passed cleanly |
| `duplicate_ids` | embedding_id 'd1' appears twice | 4 | 🚫 `partial_failure` | export | `expected_limitation` | export rejected: source palace failed integrity checks before bundle generation |
| `blank_ids` | NULL, empty, and whitespace-only embedding_ids | 4 | 🚫 `partial_failure` | export | `expected_limitation` | export rejected: source palace failed integrity checks before bundle generation |
| `missing_document` | drawer d3 has no chroma:document entry | 3 | 🚫 `partial_failure` | export | `expected_limitation` | export rejected: source palace failed integrity checks before bundle generation |
| `duplicate_document_entries` | d2 has 2 chroma:document entries | 2 | 🚫 `partial_failure` | export | `expected_limitation` | export rejected: source palace failed integrity checks before bundle generation |
| `duplicate_metadata_keys` | d2 has 'wing' duplicated | 2 | 🚫 `partial_failure` | export | `expected_limitation` | export rejected: source palace failed integrity checks before bundle generation |
| `unicode_edge_cases` | emoji/CJK/RTL/diacritics/zero-width/null-byte/astral/100K | 8 | ✅ `full_success` | — | `—` | all stages passed cleanly |
| `large_content` | 1MB + 10MB + 10K-line documents | 4 | ✅ `full_success` | — | `—` | all stages passed cleanly |
| `empty_palace` | zero drawers in embeddings table | 0 | 🚫 `partial_failure` | export | `expected_limitation` | export rejected: no drawers were extracted from the source palace |
| `missing_sqlite` | no chroma.sqlite3 file | 0 | 🚫 `partial_failure` | — | `expected_limitation` | missing sqlite file |
| `corrupted_sqlite` | chroma.sqlite3 is not a valid SQLite file | 0 | 🚫 `partial_failure` | extract | `expected_limitation` | extract rejected: source palace database query failed: file is not a database |
| `wrong_schema` | SQLite has wrong table schema (no embeddings/embedding_metadata) | 0 | 🚫 `partial_failure` | extract | `expected_limitation` | extract rejected: source palace database query failed: no such table: embeddings |
| `mixed_format_signals` | 0.6.x manifest but extra 1.x-style tables | 2 | ✅ `full_success` | — | `—` | all stages passed cleanly |
| `no_manifest` | no bridge manifest (structural detection only) | 2 | 🚫 `partial_failure` | export | `expected_limitation` | export rejected: source palace is not classified as chroma_0_6 |
| `conflicting_manifest` | manifest says 0.6.x line but 1.5.7 version | 1 | 🚫 `partial_failure` | export | `expected_limitation` | export rejected: source palace is not classified as chroma_0_6 |
| `single_drawer` | none (control) | 1 | ✅ `full_success` | — | `—` | all stages passed cleanly |
| `metadata_type_edge` | large int/float/bool/empty/negative/inf metadata values | 7 | ✅ `full_success` | — | `—` | all stages passed cleanly |

## Robustness Boundaries

### Guaranteed to work

- **valid_baseline**: clean data
- **inconsistent_wing_room**: empty/special/long wing/room names
- **unicode_edge_cases**: emoji/CJK/RTL/diacritics/zero-width/null-byte/astral/100K
- **large_content**: 1MB + 10MB + 10K-line documents
- **mixed_format_signals**: 0.6.x manifest but extra 1.x-style tables
- **single_drawer**: clean data
- **metadata_type_edge**: large int/float/bool/empty/negative/inf metadata values

### Best-effort (degraded but usable)

- _(none)_

### Correctly rejected (partial failure)

- **missing_metadata**: import rejected: target runtime rejected a batch during import
- **duplicate_ids**: export rejected: source palace failed integrity checks before bundle generation
- **blank_ids**: export rejected: source palace failed integrity checks before bundle generation
- **missing_document**: export rejected: source palace failed integrity checks before bundle generation
- **duplicate_document_entries**: export rejected: source palace failed integrity checks before bundle generation
- **duplicate_metadata_keys**: export rejected: source palace failed integrity checks before bundle generation
- **empty_palace**: export rejected: no drawers were extracted from the source palace
- **missing_sqlite**: missing sqlite file
- **corrupted_sqlite**: extract rejected: source palace database query failed: file is not a database
- **wrong_schema**: extract rejected: source palace database query failed: no such table: embeddings
- **no_manifest**: export rejected: source palace is not classified as chroma_0_6
- **conflicting_manifest**: export rejected: source palace is not classified as chroma_0_6

### Bugs / Silent corruption (hard failure)

- _(none — no silent corruption detected)_

## Recommendations

### Expected limitations (document as unsupported)

- `missing_metadata`: target runtime rejected a batch during import: batch index: 1; batch size: 5; affected drawer ids: d1, d2, d3, d4, d5; runtime error: Expected metadata to be a non-empty dict, got 0 metadata attributes in add.
- `duplicate_ids`: source palace failed integrity checks before bundle generation: duplicate source ids: d1; exported drawer count does not match sqlite embeddings rows (3 != 4)
- `blank_ids`: source palace failed integrity checks before bundle generation: blank source ids at sqlite rows 2, 3, 4; exported drawer count does not match sqlite embeddings rows (3 != 4)
- `missing_document`: source palace failed integrity checks before bundle generation: invalid chroma:document entry counts at sqlite rows 3; exported drawer count does not match sqlite embeddings rows (2 != 3)
- `duplicate_document_entries`: source palace failed integrity checks before bundle generation: invalid chroma:document entry counts at sqlite rows 2
- `duplicate_metadata_keys`: source palace failed integrity checks before bundle generation: duplicate metadata keys at sqlite rows 2
- `empty_palace`: no drawers were extracted from the source palace: sqlite path: /tmp/robustness_bsdg08bo/palaces/empty_palace/chroma.sqlite3
- `missing_sqlite`: Source palace has no chroma.sqlite3
- `corrupted_sqlite`: source palace database query failed: file is not a database: sqlite path: /tmp/robustness_bsdg08bo/palaces/corrupted_sqlite/chroma.sqlite3
- `wrong_schema`: source palace database query failed: no such table: embeddings: sqlite path: /tmp/robustness_bsdg08bo/palaces/wrong_schema/chroma.sqlite3
- `no_manifest`: source palace is not classified as chroma_0_6: detected classification: unknown
- `conflicting_manifest`: source palace is not classified as chroma_0_6: detected classification: unknown

