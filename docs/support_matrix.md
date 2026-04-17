# Support Matrix

What the reconstruction pipeline is proven to handle, and where it explicitly stops.

## Tested Source Environment

| Component | Version |
|-----------|---------|
| Python | 3.12.3 |
| ChromaDB (source) | 0.6.3 |
| MemPalace (source) | 3.1.0 |
| Palace format | `chroma_0_6` with `mempalace-bridge-manifest.json` |

## Tested Target Environment

| Component | Version |
|-----------|---------|
| Python | 3.12.3 |
| ChromaDB (target) | 1.5.7 |
| MemPalace (target) | 3.3.0 |

## Validated Input Classes

The pipeline was tested against 19 adversarial palace variants.
Results: **7 full success, 12 explicit rejections, 0 silent corruption, 0 hard failures**.

### Guaranteed to succeed

| Input class | Details |
|-------------|---------|
| Clean baseline | Standard palace with valid drawers |
| Single drawer | Minimum viable palace |
| Empty/special/long wing and room names | Unicode, whitespace, long strings |
| Unicode edge cases | Emoji, CJK, RTL, diacritics, zero-width, null-byte, astral, combining chars |
| Large content | Up to 10 MB documents, 10K-line entries |
| Mixed format signals | 0.6.x manifest with extra 1.x-style tables |
| Metadata type edge cases | Large int/float, bool, empty string, negative values, inf |

### Correctly rejected with structured error

| Input class | Stage | Reason |
|-------------|-------|--------|
| Duplicate embedding IDs | export | Integrity check catches duplicates |
| Blank/null/whitespace IDs | export | Integrity check catches invalid IDs |
| Missing `chroma:document` | export | Content validation rejects incomplete drawers |
| Duplicate `chroma:document` | export | Content validation catches duplicates |
| Duplicate metadata keys | export | Metadata validation rejects duplicates |
| Empty palace (0 drawers) | export | Minimum content requirement |
| Missing `chroma.sqlite3` | export | Pre-flight file check |
| Corrupted SQLite file | export | SQLite open fails with structured error |
| Wrong database schema | export | Table query fails with structured error |
| No bridge manifest | export | Format detector rejects non-`chroma_0_6` |
| Conflicting manifest | export | Version mismatch detection |
| Missing metadata fields | import | Target runtime rejects empty metadata dict |

## Not Tested

These scenarios have **not** been validated. The pipeline may or may not handle them:

- ChromaDB source versions other than 0.6.3
- ChromaDB target versions other than 1.5.7
- Multi-tenant ChromaDB configurations
- Palaces created without the mempalace bridge layer
- Cross-platform migration (e.g., Linux → macOS)
- Palaces exceeding 10 GB in size
- Concurrent access during export or import

## Verification Commands

```bash
# Run the adversarial robustness suite
.venv/bin/python -I scripts/investigation/robustness_harness.py

# Full test suite
.venv/bin/python -I -m pytest tests/ -v
```

## Related

- [Robustness matrix](../investigation/migration_robustness_matrix.md) — full adversarial test results
- [Limitations](limitations.md) — known boundaries and caveats
