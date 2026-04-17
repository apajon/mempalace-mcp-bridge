# Runtime Compatibility Matrix

> Controlled causality study: Is the reconstructed palace invalid for its
> intended runtime, or is the failure an artifact of loading under an
> incompatible stack?
>
> Date: 2026-04-17

---

## 1. Environment Inventory

| env_name | env_path | python_version | mempalace_version | chromadb_version | likely_role | confidence | notes |
|----------|----------|----------------|-------------------|------------------|-------------|------------|-------|
| `.venv` | `.venv/` | 3.12.3 | 3.1.0 | 0.6.3 | Stable 0.6.x path | High | Matches `pyproject.toml` pin `>=0.6,<0.7`. Used by `run.sh` and all production launch scripts. |
| `.venv-chromadb1` | `.venv-chromadb1/` | 3.12.3 | 3.3.0 | 1.5.7 | Experimental 1.x target | High | Intended target for reconstruction experiments. Has both chromadb 1.x and mempalace 3.3.0 installed and functional. |
| `.venv-mempalace31-chromadb1` | `.venv-mempalace31-chromadb1/` | 3.12.3 | — | — | Abandoned/empty | High | Empty venv — no packages installed. Not usable. |

**Launch script compatibility:**
- `run.sh` → `scripts/run_manual_mcp.sh` → hardcoded to `.venv/bin/python` → 0.6.x only
- `scripts/run_mcp_server.py` → uses `check_chromadb_version` which rejects non-0.6.x → 0.6.x only
- `scripts/run_mcp_server_exploration.py` → skips version check → can run with either env if invoked manually

---

## 2. Test Matrix Definition

### Palace Inputs

| Input | Path | Created with | Format | Verified self-loadable |
|-------|------|-------------|--------|----------------------|
| Native 0.6.x | `/tmp/compat-matrix-20996/native-06x` | `.venv` (chromadb 0.6.3) | 0.6.x (`_type` present) | Yes |
| Native 1.x | `/tmp/compat-matrix-20996/native-1x` | `.venv-chromadb1` (chromadb 1.5.7) | 1.x (`config_json_str='{}'`) | Yes |
| Reconstructed 1.x | `/tmp/compat-matrix-20996/reconstructed-1x` | Export from native-06x under `.venv`, import under `.venv-chromadb1` | 1.x (`config_json_str='{}'`) | Tested in Case B |

### Matrix Cases

| Case | Palace | Runtime | Purpose |
|------|--------|---------|---------|
| A | Native 1.x | 1.x (.venv-chromadb1) | Baseline: does a native 1.x palace work in its own stack? |
| B | Reconstructed 1.x | 1.x (.venv-chromadb1) | **Critical:** does reconstruction introduce defects? |
| C | Native 1.x | 0.6.x (.venv) | Version mismatch control: does a native 1.x palace fail in the wrong stack? |
| D | Reconstructed 1.x | 0.6.x (.venv) | Version mismatch + reconstruction: same failure signature? |
| E | Native 0.6.x | 0.6.x (.venv) | Control baseline: does same-version loading work? |
| F | Native 0.6.x | 1.x (.venv-chromadb1) | Forward compatibility: does 1.x read 0.6.x palaces? |

---

## 3. Case-by-Case Results

### Case A — Native 1.x → 1.x runtime

| Phase | Result | Detail |
|-------|--------|--------|
| 1_versions | PASS | python=3.12.3 chromadb=1.5.7 mempalace=3.3.0 |
| 2_raw_config | PASS | config_json_str='{}', has_type=False |
| 3_client_load | PASS | PersistentClient created |
| 4_collection_access | PASS | Collection loaded, count=3 |
| 5_query | PASS | Query returned 2 results: ['test-conv-001', 'test-arch-001'] |
| **Overall** | **ALL PASSED** | |

### Case B — Reconstructed 1.x → 1.x runtime

| Phase | Result | Detail |
|-------|--------|--------|
| 1_versions | PASS | python=3.12.3 chromadb=1.5.7 mempalace=3.3.0 |
| 2_raw_config | PASS | config_json_str='{}', has_type=False |
| 3_client_load | PASS | PersistentClient created |
| 4_collection_access | PASS | Collection loaded, count=3 |
| 5_query | PASS | Query returned 2 results: ['test-conv-001', 'test-arch-001'] |
| **Overall** | **ALL PASSED** | |

### Case C — Native 1.x → 0.6.x runtime

| Phase | Result | Detail |
|-------|--------|--------|
| 1_versions | PASS | python=3.12.3 chromadb=0.6.3 mempalace=3.1.0 |
| 2_raw_config | PASS | config_json_str='{}', has_type=False |
| 3_client_load | PASS | PersistentClient created |
| 4_collection_access | **FAIL** | `KeyError: '_type'` at `configuration.py:209` |
| 5_query | **FAIL** | Skipped: no collection |
| **Overall** | **FAILURES DETECTED** | |

**Failure signature:** `KeyError: '_type'` in `ConfigurationInternal.from_json()` → `sysdb._load_config_from_json_str_and_migrate()` → `get_collections()` → `get_collection()`.

### Case D — Reconstructed 1.x → 0.6.x runtime

| Phase | Result | Detail |
|-------|--------|--------|
| 1_versions | PASS | python=3.12.3 chromadb=0.6.3 mempalace=3.1.0 |
| 2_raw_config | PASS | config_json_str='{}', has_type=False |
| 3_client_load | PASS | PersistentClient created |
| 4_collection_access | **FAIL** | `KeyError: '_type'` at `configuration.py:209` |
| 5_query | **FAIL** | Skipped: no collection |
| **Overall** | **FAILURES DETECTED** | |

**Failure signature:** Identical to Case C. Same exception, same code path, same root cause.

### Case E — Native 0.6.x → 0.6.x runtime (control)

| Phase | Result | Detail |
|-------|--------|--------|
| 1_versions | PASS | python=3.12.3 chromadb=0.6.3 mempalace=3.1.0 |
| 2_raw_config | PASS | config_json_str with `_type=CollectionConfigurationInternal` |
| 3_client_load | PASS | PersistentClient created |
| 4_collection_access | PASS | Collection loaded, count=3 |
| 5_query | PASS | Query returned 2 results: ['test-conv-001', 'test-arch-001'] |
| **Overall** | **ALL PASSED** | |

### Case F — Native 0.6.x → 1.x runtime (forward compatibility)

| Phase | Result | Detail |
|-------|--------|--------|
| 1_versions | PASS | python=3.12.3 chromadb=1.5.7 mempalace=3.3.0 |
| 2_raw_config | PASS | config_json_str with `_type=CollectionConfigurationInternal` |
| 3_client_load | PASS | PersistentClient created |
| 4_collection_access | PASS | Collection loaded, count=3 |
| 5_query | PASS | Query returned 2 results: ['test-conv-001', 'test-arch-001'] |
| **Overall** | **ALL PASSED** | |

**Note:** ChromaDB 1.x is forward-compatible — it reads 0.6.x palaces without issue.

---

## 4. Summary Matrix

| Palace \ Runtime | 0.6.x (.venv) | 1.x (.venv-chromadb1) |
|-----------------|---------------|----------------------|
| Native 0.6.x | **PASS** (E) | **PASS** (F) |
| Native 1.x | **FAIL** (C) | **PASS** (A) |
| Reconstructed 1.x | **FAIL** (D) | **PASS** (B) |

---

## 5. Failure Signatures

### Signature 1: `KeyError: '_type'` (config_json_str incompatibility)

**Observed in:** Cases C and D only.

**Mechanism:**
1. Palace has `config_json_str = '{}'` (chromadb 1.x format)
2. ChromaDB 0.6.3 `ConfigurationInternal.from_json()` checks `json_map.get("_type", None)` → returns `None`
3. Type guard triggers: `"CollectionConfigurationInternal" != None`
4. Error message formatter uses `json_map['_type']` (dict access) → `KeyError`
5. Exception propagates through `sysdb.get_collections()` → `get_collection()` → swallowed by `_get_collection()`

**Classification:** Collection config incompatibility — cross-version format mismatch.

**Key observation:** This signature appears identically for **both** native 1.x and reconstructed 1.x palaces under the 0.6.x runtime. It is **not** specific to reconstruction.

### No other failure signatures observed.

---

## 6. Native vs Reconstructed Comparison (Same 1.x Stack)

This is the centerpiece comparison.

| Dimension | Native 1.x (Case A) | Reconstructed 1.x (Case B) |
|-----------|---------------------|---------------------------|
| Runtime | chromadb 1.5.7 + mempalace 3.3.0 | chromadb 1.5.7 + mempalace 3.3.0 |
| Client load | PASS | PASS |
| Collection access | PASS (count=3) | PASS (count=3) |
| Query execution | PASS (2 results) | PASS (2 results) |
| Query results | `['test-conv-001', 'test-arch-001']` | `['test-conv-001', 'test-arch-001']` |
| config_json_str | `'{}'` | `'{}'` |
| Schema columns | `[id, name, dimension, database_id, config_json_str, schema_str]` | `[id, name, dimension, database_id, config_json_str, schema_str]` |

**Conclusion:** Within the intended 1.x-compatible runtime stack, native and reconstructed palaces behave **identically**. No reconstruction-specific failure is observed.

---

## 7. Confirmed Version-Mismatch Failures

| Failure | Cases | Explanation |
|---------|-------|-------------|
| `KeyError: '_type'` when loading 1.x-format palace in 0.6.x runtime | C, D | ChromaDB 0.6.3 requires `_type` in `config_json_str`; ChromaDB 1.5.7 stores `'{}'`. This is a fundamental cross-version incompatibility in the on-disk format. |

Both native 1.x (Case C) and reconstructed 1.x (Case D) fail with the **identical signature** under the wrong runtime. The failure is fully explained by version mismatch and is independent of reconstruction.

---

## 8. Confirmed Reconstruction-Specific Failures

**None.**

The reconstructed 1.x palace (Case B) loads and queries successfully in the intended 1.x runtime stack. Its behavior is indistinguishable from a natively-created 1.x palace (Case A).

---

## 9. Additional Finding: Forward Compatibility

ChromaDB 1.5.7 successfully loads palaces created by 0.6.3 (Case F). The 1.x runtime is forward-compatible with 0.6.x palace format. The reverse (0.6.x loading 1.x palaces) is not.

This means:
- Migrating the bridge's runtime stack from 0.6.x to 1.x would resolve the load failure
- The bridge could read both old (0.6.x) and new (1.x) palaces under a 1.x runtime
- No data migration of existing 0.6.x palaces is needed if the runtime is upgraded

---

## 10. Required Output Sections

### 1. Facts

1. ChromaDB 0.6.3 stores `config_json_str` with `_type` discriminator fields.
2. ChromaDB 1.5.7 stores `config_json_str = '{}'` — empty JSON object.
3. ChromaDB 0.6.3 cannot load palaces created by 1.5.7 due to missing `_type`.
4. ChromaDB 1.5.7 can load palaces created by 0.6.3 (forward-compatible).
5. The reconstruction pipeline (`palace_reconstruction_prototype.py`) produces palaces that are valid for their target runtime.
6. A reconstructed 1.x palace is structurally identical to a native 1.x palace (same `config_json_str`, same schema, same behavior).
7. The bridge's production launch path (`run.sh` → `run_manual_mcp.sh` → `.venv`) is locked to the 0.6.x runtime.
8. `.venv-chromadb1` (chromadb 1.5.7 + mempalace 3.3.0) successfully serves both native and reconstructed 1.x palaces.

### 2. Executed Matrix

See Section 4 above. 6 cases executed, all with captured logs in `investigation/runtime_case_logs/`.

### 3. Failure Signatures

One failure signature observed: `KeyError: '_type'` at `chromadb/api/configuration.py:209`.
Appears in Cases C and D only (1.x-format palace loaded in 0.6.x runtime).
Not observed in any case where the palace was loaded in its matching runtime.

### 4. Confirmed Version-Mismatch Failures

Cases C and D: `KeyError: '_type'` when loading any 1.x-format palace (native or reconstructed) in the 0.6.x runtime.

### 5. Confirmed Reconstruction-Specific Failures

**None.** Case B (reconstructed 1.x → 1.x runtime) passed all phases identically to Case A (native 1.x → 1.x runtime).

### 6. Remaining Unknowns

1. **MCP server startup under 1.x runtime:** The matrix tested ChromaDB client load, collection access, and query execution — but did not test the full MCP stdio server launch under the 1.x stack. The bridge's launcher scripts are hardcoded to `.venv` (0.6.x). Testing MCP server startup under `.venv-chromadb1` would require manual invocation of `run_mcp_server_exploration.py` with the 1.x Python.

2. **Larger/real-world palaces:** The test used 3 synthetic drawers. A real palace with hundreds of drawers, multiple wings, and complex metadata might expose latent issues not visible in a minimal test.

3. **Embedding model compatibility:** Both environments use the default ChromaDB embedding function. If a user had configured a custom embedding function, the 1.x format change for `embedding_function` configuration might introduce a new failure class.

4. **Write-path compatibility:** The matrix tested read-only operations. Write operations (add/update drawers) under the 1.x runtime with a reconstructed palace were not tested.

### 7. Best Current Verdict

**Pure version mismatch.**

Every observed failure is fully explained by loading a 1.x-format palace in the 0.6.x runtime. No reconstruction-specific failure remains after controlling for runtime version.

The reconstructed palace works correctly in the intended 1.x runtime stack. The reconstruction pipeline is not introducing defects visible at the runtime load/query level.

### 8. Next Most Important Experiment

**Test full MCP server startup and tool execution under the 1.x runtime stack.**

Specifically:
```bash
MEMPALACE_PALACE_PATH=/tmp/compat-matrix-20996/reconstructed-1x \
  .venv-chromadb1/bin/python scripts/run_mcp_server_exploration.py
```

This would confirm that the MCP tool layer (tool registration, tool invocation, stdio transport) works end-to-end under chromadb 1.5.7 + mempalace 3.3.0, not just the underlying ChromaDB client operations.

If this succeeds, the path forward is clear: align the bridge's runtime stack to 1.x.

---

## Appendix: Commands Used

### Palace creation
```bash
# Native 0.6.x
.venv/bin/python scripts/investigation/create_native_palace.py /tmp/compat-matrix-20996/native-06x

# Native 1.x
.venv-chromadb1/bin/python scripts/investigation/create_native_palace.py /tmp/compat-matrix-20996/native-1x

# Reconstructed 1.x (export + import)
.venv/bin/python scripts/palace_reconstruction_prototype.py export \
  --source-palace /tmp/compat-matrix-20996/native-06x \
  --output-dir /tmp/compat-matrix-20996/export-bundle

.venv-chromadb1/bin/python scripts/palace_reconstruction_prototype.py import \
  --export-dir /tmp/compat-matrix-20996/export-bundle \
  --target-palace /tmp/compat-matrix-20996/reconstructed-1x
```

### Matrix execution
```bash
# Case A: native 1.x → 1.x runtime
.venv-chromadb1/bin/python scripts/investigation/runtime_load_test.py /tmp/compat-matrix-20996/native-1x

# Case B: reconstructed 1.x → 1.x runtime
.venv-chromadb1/bin/python scripts/investigation/runtime_load_test.py /tmp/compat-matrix-20996/reconstructed-1x

# Case C: native 1.x → 0.6.x runtime
.venv/bin/python scripts/investigation/runtime_load_test.py /tmp/compat-matrix-20996/native-1x

# Case D: reconstructed 1.x → 0.6.x runtime
.venv/bin/python scripts/investigation/runtime_load_test.py /tmp/compat-matrix-20996/reconstructed-1x

# Case E: native 0.6.x → 0.6.x runtime (control)
.venv/bin/python scripts/investigation/runtime_load_test.py /tmp/compat-matrix-20996/native-06x

# Case F: native 0.6.x → 1.x runtime (forward compat)
.venv-chromadb1/bin/python scripts/investigation/runtime_load_test.py /tmp/compat-matrix-20996/native-06x
```

### Log files
All raw logs stored in `investigation/runtime_case_logs/`:
- `case_A_native1x_on_1x.log`
- `case_B_reconstructed1x_on_1x.log`
- `case_C_native1x_on_06x.log`
- `case_D_reconstructed1x_on_06x.log`
- `case_E_native06x_on_06x.log`
- `case_F_native06x_on_1x.log`
