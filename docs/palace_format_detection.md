# Palace format detection

## Goal

Detect which storage/version line a palace most likely belongs to **before** opening it with ChromaDB or MemPalace.

This detector is intentionally conservative. It exists to prevent unsafe actions, not to force compatibility.

## Output classes

- `chroma_0_6`
- `chroma_1_x`
- `unknown`

## Decision rules

### 1. Manifest-first

If `mempalace-bridge-manifest.json` is present, the detector prefers that explicit metadata.

Priority inside the manifest:

1. `compatibility_line`
2. `chromadb_version`

Rules:

- `compatibility_line == "chromadb-0.6.x"` → `chroma_0_6`
- `compatibility_line == "chromadb-1.x"` or starts with `chromadb-1.` → `chroma_1_x`
- `chromadb_version` on `0.6.x` → `chroma_0_6`
- `chromadb_version` on `1.x` → `chroma_1_x`
- if manifest fields conflict, detection resolves to `unknown`

### 2. Structural fallback

If the manifest is missing or does not provide a usable answer, the detector inspects `chroma.sqlite3` without opening the palace through ChromaDB.

Current structural rule:

- if **every** `collections.config_json_str` entry contains `_type = "CollectionConfigurationInternal"`, classify as `chroma_0_6`

Ambiguous structural cases resolve to `unknown`, including:

- missing `chroma.sqlite3`
- unreadable SQLite
- missing `collections` table
- empty `collections` table
- invalid JSON in `config_json_str`
- all configs untyped (`{}`)
- mixed typed and untyped configs

## Why `1.x` fallback stays conservative

A `1.x` palace can use a SQLite schema similar to a `0.6.x` palace. One structural difference is untyped `config_json_str` values (`{}`), but that shape is **not unique** to `1.x`; it can also appear in older incompatible storage.

Because of that, the detector does **not** infer `chroma_1_x` from structure alone in this first version.

## Confidence levels

- `high` — explicit manifest evidence
- `medium` — structural evidence strong enough for `chroma_0_6`
- `low` — ambiguous or unknown result

## Usage

```bash
.venv/bin/python scripts/palace_format_detector.py ~/.mempalace/palace --pretty
```

## Stable safety gate

The stable bridge now uses a narrow safety gate before risky palace operations.

Guarded flows:

- `scripts/init_palace.sh`
- `scripts/mine_sample_data.sh`
- `scripts/check_palace_health.sh`
- `scripts/palace_legacy_repair.py` (the only repair path)
- `scripts/run_mcp_server.py`
- `verify.sh` (before palace health/open checks)

Policy on the stable path:

- `chroma_0_6` → allowed for every action
- `chroma_1_x` → blocked
- `unknown` → blocked for **read** and **write**
- `unknown` + `repair` → allowed **only** when the narrow legacy repair preflight
  passes (see below)

Examples:

```bash
python3 scripts/palace_safety_gate.py --action read ~/.mempalace/palace
python3 scripts/palace_safety_gate.py --action write ~/.mempalace/palace
python3 scripts/palace_safety_gate.py --action repair ~/.mempalace/palace
```

The gate does not migrate or retry with another runtime. It only decides whether
the stable bridge should proceed.

## Three distinct notions

These must never be conflated:

| Notion | Question it answers | Where |
|---|---|---|
| **Runtime compatibility** (`chroma_0_6` / `chroma_1_x` / `unknown`) | may the pinned 0.6.x bridge open this palace at all? | `palace_format_detector.py` |
| **Storage profile** (`chroma_0_6_native` / `chroma_1_x_migrated` / `unknown`) | *what actually wrote the SQLite schema?* | `palace_legacy_repair.detect_storage_profile()` |
| **Repair eligibility** (eligible / not) | may this untyped palace be repaired, and under which profile? | `palace_legacy_repair.evaluate_legacy_repair_eligibility()` |

A palace can be *structurally ambiguous as a format* while being *eligible for a
known legacy migration*. Conversely, a palace can be *runtime-compatible* without
being a 0.6.x-native schema.

> `chroma_0_6` is a **runtime-compatibility** verdict, not a provenance claim.
> A palace whose schema was written by ChromaDB 1.x and then reopened by 0.6.x is
> classified `chroma_0_6` (0.6.3 can read it — its `SqlDB.decode_seq_id` accepts
> `int`, and 0.6.3 names its columns explicitly so the extra 1.x tables/columns are
> ignored), while its **storage profile** is `chroma_1_x_migrated`. The manifest
> records both, so no false provenance is stored.

## Storage profiles

| Profile | Migrations | `seq_id` stored | `schema_str` | `acquire_write`, `embedding_metadata_array` |
|---|---|---|---|---|
| `chroma_0_6_native` | `sysdb 9`, `metadb 4`, `embeddings_queue 2` | blob | absent | absent |
| `chroma_1_x_migrated` | `sysdb 10`, `metadb 6`, `embeddings_queue 2` | integer | present | present |

Both profiles are matched **exactly**; a palace that matches neither (including a
half-migrated one — e.g. integer `seq_id` with 0.6.x migrations) is reported as
`unknown` and is never repaired.

## Narrow legacy repair

Detecting `unknown` is not the same as "must never be repaired". A legacy palace
that stored an untyped `config_json_str` of `{}` is safely repairable into the
typed configuration. That possibility is handled by a **separate, much stricter**
preflight in `scripts/palace_legacy_repair.py`, which is the only thing that can
authorise a `repair` on an `unknown` palace.

Eligibility requires **all** of these:

| Invariant | Check |
|---|---|
| Not another storage line | detection is not `chroma_1_x` |
| Database present | `chroma.sqlite3` exists |
| Manifest not contradictory | no manifest, or a manifest confirming the `chromadb-0.6.x` compatibility line |
| SQLite opens read-only | the database is readable |
| SQLite integrity | `PRAGMA integrity_check` returns `ok` |
| Config value | every `config_json_str` is exactly `{}` — **not** `NULL`, not `''`, not mixed with typed values, not non-empty untyped, not invalid JSON |
| Known storage profile | the schema matches `chroma_0_6_native` **or** `chroma_1_x_migrated` exactly |
| Expected collection | the configured MemPalace collection is present |

The profile then adds its own structural checks (migrations, table set, extra
tables, `collections` columns, real `typeof(seq_id)`, no leftover `int_seq_id`,
`embedding_metadata.bool_value`).

Any single failure makes the palace ineligible and nothing is mutated. This is
deliberately fail-closed.

> **`NULL` is deliberately not repairable.** ChromaDB 0.6.x opens a `NULL`
> configuration without error (verified), so such a palace needs no mutation and
> is left untouched. An empty string is a different failure shape and is also
> refused rather than guessed at.

When the palace is eligible, the repair:

1. creates a consistent backup via the SQLite backup API, named
   `chroma.sqlite3.bak-<UTC timestamp>` (an existing backup is never overwritten);
2. rewrites the untyped `config_json_str` values inside a single transaction
   (rollback on any error);
3. re-detects the palace and opens it through the real stack as a smoke test;
4. if post-repair validation fails, restores the backup;
5. only after a successful repair **and** a successful read does it write
   `mempalace-bridge-manifest.json` (and only when no valid manifest already
   exists), recording the detected **storage profile** alongside the runtime
   compatibility line.

The manifest is never marked as compatible before the repair and the smoke test
have both succeeded, and it never records a storage profile that was not actually
observed.

Inspect the profile without touching anything:

```bash
.venv/bin/python scripts/palace_legacy_repair.py ~/.mempalace/palace --detect-profile
```

Run the preflight manually with:

```bash
.venv/bin/python scripts/palace_legacy_repair.py ~/.mempalace/palace          # preflight only
.venv/bin/python scripts/palace_legacy_repair.py ~/.mempalace/palace --apply  # apply
```

## Example outputs

### Manifest-backed `0.6.x`

```json
{
  "palace_path": "/home/user/.mempalace/palace",
  "classification": "chroma_0_6",
  "confidence": "high",
  "evidence": [
    {
      "source": "manifest",
      "detail": "compatibility_line='chromadb-0.6.x'"
    }
  ]
}
```

### Manifest-backed `1.x`

```json
{
  "palace_path": "/tmp/palace",
  "classification": "chroma_1_x",
  "confidence": "high",
  "evidence": [
    {
      "source": "manifest",
      "detail": "chromadb_version='1.5.7'"
    }
  ]
}
```

### Ambiguous storage

```json
{
  "palace_path": "/tmp/palace",
  "classification": "unknown",
  "confidence": "low",
  "evidence": [
    {
      "source": "structure",
      "detail": "all collections.config_json_str entries are untyped; this is ambiguous and not strong enough to distinguish chroma_1_x from older incompatible storage"
    }
  ]
}
```
