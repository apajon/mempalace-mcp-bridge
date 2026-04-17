# Limitations

Explicit boundaries of the reconstruction pipeline. These are not bugs — they are
deliberate scope constraints.

## Pipeline Scope

The reconstruction pipeline migrates a **single MemPalace** from a ChromaDB 0.6.x
runtime to a ChromaDB 1.x runtime. It is:

- **Non-destructive** — the source palace is never modified
- **Offline** — both source and target must be stopped during migration
- **Single-palace** — one palace per invocation; no batch or multi-tenant support
- **One-way** — export is from 0.6.x only; there is no 1.x → 0.6.x path

## Version Constraints

| Constraint | Tested Value | Notes |
|------------|-------------|-------|
| Source ChromaDB | 0.6.3 | Other 0.6.x versions may work but are untested |
| Target ChromaDB | 1.5.7 | Other 1.x versions may work but are untested |
| Python | 3.12.3 | Required by both runtimes |
| Palace format | `chroma_0_6` | Must have `mempalace-bridge-manifest.json` |

## Data Constraints

The pipeline rejects palaces with:

- Duplicate, blank, or null embedding IDs
- Missing or duplicate `chroma:document` entries
- Duplicate metadata keys on the same embedding
- Zero drawers (empty palaces)
- Missing metadata fields (target ChromaDB 1.x requires non-empty metadata)

These are validated at export time with clear error messages.

## Operational Constraints

- **No concurrent access**: the source and target palaces must not be accessed by
  other processes during migration
- **Disk space**: the work directory must have enough space for the export bundle
  (drawers.jsonl + metadata), roughly proportional to source palace size
- **Separate Python environments**: source (0.6.x) and target (1.x) typically need
  different virtualenvs due to incompatible ChromaDB dependencies
- **Target must not exist**: the import step creates a new palace; it will not
  overwrite or merge into an existing one

## What This Pipeline Does Not Do

- **No incremental sync** — every migration is a full export/import cycle
- **No schema evolution** — metadata is transferred as-is; no field renaming or
  type coercion beyond what ChromaDB natively handles
- **No embedding re-computation** — vectors are copied verbatim; if the source
  used a different embedding model, vectors will be preserved but not recomputed
- **No MCP integration testing** — MCP runtime validation (`--with-mcp-runtime`)
  is an optional comparison step, not a migration guarantee
- **No rollback** — if import fails partway, the target directory may contain
  partial data; delete it and re-run

## Known Edge Cases

- Documents up to 10 MB have been tested successfully; behavior above that is
  unknown
- Metadata values including `inf`, `NaN` floats, and extremely large integers
  pass through export but their round-trip fidelity through ChromaDB 1.x
  depends on the target runtime
- Null bytes in documents are preserved in export but may be rejected by
  downstream consumers

## Related

- [Support matrix](support_matrix.md) — what has been tested and proven
- [Error model](error_model.md) — how failures are reported
