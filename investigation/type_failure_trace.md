# `_type` Runtime Failure Trace

> Full trace of the `_type` failure that prevents reconstructed ChromaDB 1.x
> palaces from loading in the MemPalace MCP runtime.
>
> Date: 2025-04-17

---

## TL;DR

A palace created under **chromadb 1.5.7** stores `config_json_str = '{}'` (empty
JSON object). When **chromadb 0.6.3** tries to load this palace, it expects a
`_type` discriminator field in `config_json_str`. The type guard detects the
mismatch but a **bug in the error message formatting** raises `KeyError` instead
of the intended `ValueError`. MemPalace's `_get_collection()` catches all
exceptions silently and returns `{"error": "No palace found"}`.

---

## 1. Environment

| Component | Version | Location |
|-----------|---------|----------|
| chromadb (runtime) | 0.6.3 | `.venv/` |
| chromadb (1.x target) | 1.5.7 | `.venv-chromadb1/` |
| mempalace | 3.0+ (runtime), 3.3.0 (1.x env) | vendored in both |
| Python | 3.12.3 | system |

---

## 2. The Configuration Format Break

### ChromaDB 0.6.3 — `config_json_str`

```json
{
  "hnsw_configuration": {
    "space": "l2",
    "ef_construction": 100,
    "ef_search": 100,
    "num_threads": 12,
    "M": 16,
    "resize_factor": 1.2,
    "batch_size": 100,
    "sync_threshold": 1000,
    "_type": "HNSWConfigurationInternal"
  },
  "_type": "CollectionConfigurationInternal"
}
```

### ChromaDB 1.5.7 — `config_json_str`

```json
{}
```

**ChromaDB 1.5.7 completely rewrote the configuration model:**

- `ConfigurationInternal` class hierarchy → `CollectionConfiguration` TypedDict
- `_type` discriminator → removed entirely
- `hnsw_configuration` key → `hnsw` (in the new TypedDict model)
- New system: `chromadb/api/collection_configuration.py`
- Loader: `load_collection_configuration_from_json_str()` (ignores `_type`)
- 1.5.7's `from_json_str()` handles `{}` gracefully: `return cls.from_json(config_json) if config_json else cls()`

The `schema_str` column was also added in 1.x (absent in 0.6.3).

---

## 3. Failure Path — Step by Step

### Entry point

```
mempalace.mcp_server._get_collection()
  → client.get_collection("mempalace_drawers")
```

### Call stack (observed from reproduction)

```
mcp_server.py:_get_collection()
  └─ chromadb.api.client.ClientAPI.get_collection()
       └─ chromadb.api.segment.SegmentAPI.get_collection()
            └─ chromadb.db.mixins.sysdb.SqlSysDB.get_collections()  [line 521]
                 └─ sysdb._load_config_from_json_str_and_migrate()  [line 886]
                      └─ CollectionConfigurationInternal.from_json_str(json_str)
                           └─ ConfigurationInternal.from_json_str()  [line 188]
                                └─ ConfigurationInternal.from_json()  [line 207-209]
                                     └─ KeyError: '_type'  ← THE FAILURE
```

### Detailed code walk

#### Step 1: `_get_collection()` (mempalace/mcp_server.py:115-127)

```python
def _get_collection(self):
    try:
        client = self._get_client()
        return client.get_collection("mempalace_drawers")
    except Exception:          # ← catches EVERYTHING
        return None            # ← user sees "No palace found"
```

#### Step 2: `get_collections()` (sysdb.py:521)

```python
configuration = self._load_config_from_json_str_and_migrate(
    config_json_str, collection_id_str
)
```

#### Step 3: `_load_config_from_json_str_and_migrate()` (sysdb.py:874-921)

```python
try:
    return CollectionConfigurationInternal.from_json_str(json_str)
except InvalidConfigurationError as error:
    # migration logic for swapped batch_size/sync_threshold
    ...
```

**Gap:** Only catches `InvalidConfigurationError`. `KeyError` and `ValueError`
propagate uncaught.

#### Step 4: `from_json_str()` (configuration.py:180-188)

```python
@classmethod
def from_json_str(cls, json_str: str) -> Self:
    try:
        config_json = json.loads(json_str)
    except json.JSONDecodeError:
        raise ValueError(...)
    return cls.from_json(config_json)    # ← 0.6.3: always calls from_json
```

**Note:** 1.5.7 has `return cls.from_json(config_json) if config_json else cls()`
— handles empty dicts. 0.6.3 does not.

#### Step 5: `from_json()` — THE BUG (configuration.py:207-209)

```python
@classmethod
def from_json(cls, json_map: Dict[str, Any]) -> Self:
    if cls.__name__ != json_map.get("_type", None):      # line 207
        raise ValueError(                                 # line 208
            f"Trying to instantiate configuration of type {cls.__name__} "
            f"from JSON with type {json_map['_type']}"    # line 209 ← KeyError
        )
```

**Line 207:** `json_map.get("_type", None)` returns `None`.
`"CollectionConfigurationInternal" != None` → `True` → enters error branch.

**Line 209:** Error message uses `json_map['_type']` (dict key access).
Since `_type` is NOT in `json_map`, this raises `KeyError: '_type'`.

**Result:** `KeyError` instead of `ValueError`. This is a bug in chromadb 0.6.3.

#### Step 6: Exception propagation

```
KeyError at from_json:209
  ↓ (not caught by _load_config_from_json_str_and_migrate, which only catches InvalidConfigurationError)
  ↓ (propagates through get_collections → get_collection)
  ↓ (caught by _get_collection's bare except Exception)
  ↓ → returns None
  ↓ → _no_palace() → {"error": "No palace found"}
```

---

## 4. Reproduction

Script: `investigation/reproduce_type_failure.py`

```bash
.venv/bin/python investigation/reproduce_type_failure.py
```

Creates a valid 0.6.3 palace, corrupts `config_json_str` to `'{}'`, then
demonstrates all three phases:
1. Direct `get_collection()` → `KeyError: '_type'`
2. Simulated `_get_collection()` → `None` → "No palace found"
3. Instrumented load showing raw config state

Cross-version inspection: `investigation/inspect_config_format.py`

```bash
.venv-chromadb1/bin/python investigation/inspect_config_format.py   # 1.5.7 → config='{}'
.venv/bin/python investigation/inspect_config_format.py             # 0.6.3 → config with _type
```

---

## 5. Provenance: How the Palace Gets `_type`-less Config

### Path A: Reconstruction under 1.5.7

1. `scripts/reconstruct.sh` imports drawers into a target palace using
   `--target-python` pointing to a 1.5.7 environment.
2. `palace_reconstruction_prototype.py` calls `client.create_collection()`.
3. Under 1.5.7, `create_collection()` stores `config_json_str = '{}'`.
4. The reconstructed palace is now in 1.5.7 format.
5. When the MCP bridge (pinned to chromadb 0.6.3) tries to load it → failure.

### Path B: Direct upgrade

1. User upgrades their environment to chromadb 1.x.
2. 1.x creates collections with empty `config_json_str`.
3. If the user later downgrades or the MCP bridge still uses 0.6.3 → failure.

### Path C: Manually created/migrated palace

Any palace whose `config_json_str` is `'{}'` or lacks `_type` will trigger this
failure under 0.6.3.

---

## 6. Answers to the Four Questions

### Q1: What is failing?

`ConfigurationInternal.from_json()` at `chromadb/api/configuration.py:209` raises
`KeyError: '_type'` when deserializing a `config_json_str` that lacks the `_type`
discriminator field.

### Q2: What object is missing `_type`?

The `config_json_str` column in the `collections` table of `chroma.sqlite3`. This
is a JSON string that, under chromadb 0.6.3, must contain
`"_type": "CollectionConfigurationInternal"` at the top level (and
`"_type": "HNSWConfigurationInternal"` nested inside `hnsw_configuration`).

### Q3: Where should `_type` have come from?

`ConfigurationInternal.to_json()` stamps `json_dict["_type"] = self.__class__.__name__`
at serialization time (configuration.py:200). Under 0.6.3, `create_collection()`
calls `configuration.to_json_str()` which includes `_type`. Under 1.5.7, the
configuration system was rewritten and `_type` is no longer used.

### Q4: Do we already know enough to fix reconstruction?

**Yes.** Three non-exclusive fix options:

1. **Post-import config injection** (simplest, in the bridge):
   After reconstruction imports drawers, inject the 0.6.3 `_type` fields into
   `config_json_str` if they're missing. `check_palace_health.sh` already has
   detection logic for this (line 92).

2. **Pre-load migration** (in the bridge's MCP launcher):
   Before `_get_collection()`, check `config_json_str` and patch if `_type` is
   absent. This would make the runtime tolerant of 1.x palaces.

3. **Upgrade chromadb dependency** (strategic):
   Upgrade mempalace's chromadb dependency to 1.x, eliminating the format
   incompatibility entirely. This requires mempalace upstream changes.

---

## 7. Contributing Factors

| Factor | Severity | Description |
|--------|----------|-------------|
| Bug in error message | Medium | `json_map['_type']` at line 209 should be `json_map.get('_type', '<missing>')`. Raises `KeyError` instead of `ValueError`. |
| Bare `except Exception` | High | `_get_collection()` swallows ALL exceptions. The real error is invisible to the user. |
| No config format migration | High | 0.6.3's `_load_config_from_json_str_and_migrate()` only handles one migration case (swapped batch_size/sync_threshold). It has no handler for the empty-config case. |
| Breaking config format | Root cause | 1.5.7 removed `_type` and the entire `ConfigurationInternal` class hierarchy. No forward-compatibility path from 0.6.3. |

---

## 8. Open Questions

1. Does mempalace 3.3.0 (in `.venv-chromadb1`) work correctly with chromadb 1.5.7?
   If so, the fix might be to match the bridge's runtime to the target version.

2. Should the bridge support both config formats simultaneously (graceful
   degradation), or should it enforce a single version?

3. Is there a chromadb migration path that handles the 0.6→1.x config format
   change? (Initial evidence suggests no — 1.5.7 just ignores the old format.)
