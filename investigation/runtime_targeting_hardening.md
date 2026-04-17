# Runtime Targeting Hardening

> Audit, findings, and implemented safeguards.
> Date: 2026-04-17

---

## Problem Statement

The bridge's production launch path is locked to the 0.6.x runtime (`.venv`, chromadb 0.6.3).
If a palace is created or reconstructed under chromadb 1.x, loading it through the production
path fails with `KeyError: '_type'` — an opaque, misleading error.

The root cause is a cross-version runtime/palace format mismatch, not a reconstruction defect.
The fix is twofold:
1. **Detect** the mismatch before it causes the opaque failure
2. **Explain** it with actionable diagnostics

---

## Audit Results

### Scripts that hardcode `.venv/bin/python`

| Script | Hardcoded? | Consequence |
|--------|-----------|-------------|
| `run.sh` | Yes (via `run_manual_mcp.sh`) | Forces 0.6.x runtime for MCP server |
| `scripts/run_manual_mcp.sh` | Yes | Launcher is 0.6.x-only |
| `scripts/check_chromadb_version.sh` | Yes | Version check always against 0.6.x env |
| `scripts/verify_install.sh` | Yes | Verification assumes 0.6.x |
| `scripts/check_palace_health.sh` | Yes | Health checks use 0.6.x runtime |
| `scripts/init_palace.sh` | Yes | Palace creation in 0.6.x |
| `scripts/reconstruct.sh` | Defaults to `.venv` | Overridable via `--source-python`/`--target-python` |
| `verify.sh` | Yes | Top-level verify uses 0.6.x |
| `setup.sh` | Yes (via bootstrap) | Setup creates 0.6.x env |
| `update.sh` | Yes | Update targets 0.6.x |

### Scripts with version checks

| Script | Check type | What it enforces |
|--------|-----------|-----------------|
| `scripts/check_chromadb_version.py` | `importlib.metadata` | Rejects anything not `0.6.x` |
| `scripts/run_mcp_server.py` | Three-layer check | Version → safety gate → runtime compat |
| `scripts/palace_safety_gate.py` | SQLite inspection | Blocks `chroma_1_x` palaces |
| `scripts/palace_format_detector.py` | SQLite + manifest | Classifies palace format |
| `verify.sh` | Regex on version string | Rejects non-0.6.x |

### Gap: `run_mcp_server_exploration.py`

Previously had **zero** checks — silently loaded any palace in any runtime.
Now emits a warning when a mismatch is detected but does not block (exploration mode).

---

## Implemented Changes

### 1. `scripts/runtime_compat.py` (NEW)

Centralised palace/runtime compatibility guard. Provides:

- `classify_chromadb_version(version) → "0.6.x" | "1.x" | "unknown"`
- `probe_palace_format(path) → "0.6.x" | "1.x" | "empty" | "unreadable"`
- `is_compatible(palace_format, runtime_line) → bool | None`
- `diagnose(palace_path) → CompatDiagnostic`

The compatibility matrix encodes the known truth:

| Palace format | Runtime 0.6.x | Runtime 1.x |
|--------------|:---:|:---:|
| 0.6.x | ✅ | ✅ |
| 1.x | ❌ | ✅ |

The `diagnose()` function produces an actionable error message for the known-incompatible case:

```
Palace at /path/to/palace was created with chromadb 1.x (config_json_str lacks '_type'),
but this runtime uses chromadb 0.6.3 (0.6.x line). ChromaDB 0.6.x cannot load 1.x-format
palaces — it will fail with KeyError: '_type' in ConfigurationInternal.from_json().

Use a chromadb 1.x environment to load this palace, or reconstruct it for 0.6.x.
See: docs/troubleshooting.md#chromadb-version-incompatibility
```

### 2. `scripts/run_mcp_server.py` (MODIFIED)

Replaced the ad-hoc `_check_config_type()` function with `runtime_compat.diagnose()`.
The launcher now has a clean three-layer guard:

1. `get_unsupported_reason()` — rejects non-0.6.x chromadb
2. `evaluate_palace_safety()` — blocks 1.x-classified palaces
3. `diagnose()` — catches the specific mismatch with precise diagnostics

### 3. `scripts/run_mcp_server_exploration.py` (MODIFIED)

Now calls `runtime_compat.diagnose()` and emits a `[WARN]` if a mismatch is detected.
Does NOT block — exploration mode is explicitly opt-in.

### 4. `tests/test_runtime_compat.py` (NEW)

19 unit tests covering:
- Version classification (10 cases)
- Compatibility matrix (5 cases)
- Palace format probing (4 cases with synthetic SQLite files)

---

## What this does NOT change

- The stable launch path (`run.sh`) remains 0.6.x-only — no regression.
- No shell scripts were modified — their hardcoded paths remain correct for the stable path.
- `pyproject.toml` still pins `chromadb>=0.6,<0.7`.
- `reconstruct.sh` still defaults to `.venv` but remains overridable.

---

## Verification

```bash
# Mismatch detection (should fail with clear error):
.venv/bin/python scripts/runtime_compat.py /tmp/rich-migration-test-20996/native-1x

# Compatible load (should pass):
.venv-chromadb1/bin/python scripts/runtime_compat.py /tmp/rich-migration-test-20996/native-1x

# Same-version load (should pass):
.venv/bin/python scripts/runtime_compat.py /tmp/rich-migration-test-20996/native-06x

# Forward compat (should pass):
.venv-chromadb1/bin/python scripts/runtime_compat.py /tmp/rich-migration-test-20996/native-06x
```

All four tested and verified — see runtime compatibility matrix study.
