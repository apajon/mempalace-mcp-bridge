# Runtime Inputs

> Palace inputs used in the runtime compatibility matrix.
> Date: 2026-04-17

---

## 1. Native 0.6.x Palace

| Field | Value |
|-------|-------|
| Path | `/tmp/compat-matrix-20996/native-06x` |
| Created by | `scripts/investigation/create_native_palace.py` |
| Environment | `.venv` (chromadb 0.6.3, mempalace 3.1.0, Python 3.12.3) |
| Format generation | ChromaDB 0.6.x |
| config_json_str | `{"hnsw_configuration": {..., "_type": "HNSWConfigurationInternal"}, "_type": "CollectionConfigurationInternal"}` |
| Schema columns | `id, name, dimension, database_id, config_json_str` |
| Content | 3 drawers (architecture, conventions, debugging) |
| Verified loadable | Yes — roundtrip verified during creation |
| Role | Control baseline for 0.6.x runtime, source for reconstruction |

## 2. Native 1.x Palace

| Field | Value |
|-------|-------|
| Path | `/tmp/compat-matrix-20996/native-1x` |
| Created by | `scripts/investigation/create_native_palace.py` |
| Environment | `.venv-chromadb1` (chromadb 1.5.7, mempalace 3.3.0, Python 3.12.3) |
| Format generation | ChromaDB 1.x |
| config_json_str | `{}` |
| Schema columns | `id, name, dimension, database_id, config_json_str, schema_str` |
| Content | 3 drawers (identical logical content as native 0.6.x) |
| Verified loadable | Yes — roundtrip verified during creation |
| Role | Reference for "does a native 1.x palace load in the 1.x stack?" |

## 3. Reconstructed 1.x Palace

| Field | Value |
|-------|-------|
| Path | `/tmp/compat-matrix-20996/reconstructed-1x` |
| Created by | Reconstruction pipeline: export from native 0.6.x, import under 1.x |
| Export step | `.venv/bin/python scripts/palace_reconstruction_prototype.py export --source-palace .../native-06x --output-dir .../export-bundle` |
| Import step | `.venv-chromadb1/bin/python scripts/palace_reconstruction_prototype.py import --export-dir .../export-bundle --target-palace .../reconstructed-1x` |
| Format generation | ChromaDB 1.x (imported under `.venv-chromadb1`) |
| config_json_str | `{}` |
| Schema columns | `id, name, dimension, database_id, config_json_str, schema_str` |
| Content | 3 drawers (same logical content, reconstructed) |
| Verified loadable | Yes — verified during Case B matrix test |
| Role | Critical comparison target: does reconstruction introduce defects? |

## Why These Inputs Are Representative

- All three palaces contain **identical logical content** (same 3 drawers, same metadata).
- The native 0.6.x and native 1.x palaces were created by the **same script** using the **same API calls**, differing only in which ChromaDB version executed them.
- The reconstructed palace was produced by the **actual reconstruction pipeline** in this repository (`palace_reconstruction_prototype.py`), not a simplified substitute.
- The content is minimal but sufficient: it includes multiple drawers with metadata wings/rooms, enough for collection access and query tests.

## Export Bundle

| Field | Value |
|-------|-------|
| Path | `/tmp/compat-matrix-20996/export-bundle` |
| Created by | `palace_reconstruction_prototype.py export` |
| Source | native-06x palace |
| Contents | `drawers.jsonl`, retrieval queries, usage scenarios |
| Source detection | `chroma_0_6` (medium confidence) |
