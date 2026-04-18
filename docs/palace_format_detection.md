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

A `1.x` palace uses a SQLite schema similar to a `0.6.x` palace. The main structural difference is untyped `config_json_str` values (`{}`), but that shape is **not unique** to `1.x`; it can also appear in older incompatible storage.

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
- `scripts/run_mcp_server.py`
- `verify.sh` (before palace health/open checks)

Policy on the stable path:

- `chroma_0_6` → allowed
- `chroma_1_x` → blocked
- `unknown` → blocked

Examples:

```bash
python3 scripts/palace_safety_gate.py --action read ~/.mempalace/palace
python3 scripts/palace_safety_gate.py --action write ~/.mempalace/palace
```

The gate does not migrate, repair, or retry with another runtime. It only decides whether the stable bridge should proceed.

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
