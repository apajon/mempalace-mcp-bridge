# `_type` Usages Inventory

> Generated from investigation of the `_type` runtime failure in MemPalace MCP Bridge.
> Date: 2025-04-17

---

## 1. chromadb/api/configuration.py (vendored, 0.6.3)

File: `.venv/lib/python3.12/site-packages/chromadb/api/configuration.py`

### 1.1 `to_json()` — line 200

```python
json_dict["_type"] = self.__class__.__name__
```

**Purpose:** Stamps the concrete class name into the serialized JSON dict so that
`from_json()` can verify type identity on deserialization.

Written by: `ConfigurationInternal.to_json()` (base class).
Inherited by: `CollectionConfigurationInternal`, `HNSWConfigurationInternal`.

### 1.2 `from_json()` — type guard — line 207

```python
if cls.__name__ != json_map.get("_type", None):
```

**Purpose:** Ensures the JSON being deserialized was produced by the same class
that is now loading it. If `_type` is missing, `.get()` returns `None`, and the
check evaluates to `True` (mismatch), entering the error branch.

### 1.3 `from_json()` — error message — line 209 (BUG)

```python
raise ValueError(
    f"Trying to instantiate configuration of type {cls.__name__} "
    f"from JSON with type {json_map['_type']}"
)
```

**Purpose:** Intended to raise `ValueError` with a descriptive message.

**Bug:** Uses `json_map['_type']` (dict key access) instead of
`json_map.get('_type')`. When `_type` is absent, this line itself raises
`KeyError: '_type'` **before** the intended `ValueError` is constructed.

### 1.4 `from_json()` — skip during iteration — line 214

```python
if name == "_type":
    continue
```

**Purpose:** Excludes the `_type` key when building `ConfigurationParameter` list
from deserialized JSON. The `_type` is metadata, not a configuration parameter.

### 1.5 `HNSWConfigurationInternal` — nested `_type`

The nested HNSW config written by `to_json()` also receives a `_type` stamp
(`"HNSWConfigurationInternal"`), since `HNSWConfigurationInternal` inherits
from `ConfigurationInternal`.

---

## 2. chromadb/db/mixins/sysdb.py (vendored, 0.6.3)

File: `.venv/lib/python3.12/site-packages/chromadb/db/mixins/sysdb.py`

### 2.1 `get_collections()` — line 521

```python
configuration = self._load_config_from_json_str_and_migrate(
    config_json_str, collection_id_str
)
```

Reads `config_json_str` column from SQLite and passes it to the migration/load
helper.

### 2.2 `_load_config_from_json_str_and_migrate()` — line 886

```python
return CollectionConfigurationInternal.from_json_str(json_str)
```

Calls `from_json_str()` → `from_json()` → hits the `_type` check.
Exception handler here only catches `InvalidConfigurationError`, NOT `KeyError`
or `ValueError`.

### 2.3 `create_collection()` — line ~330

```python
configuration.to_json_str()
```

Writes the serialized config (including `_type`) to the `config_json_str` column.
Collections created via chromadb 0.6.3 API always have `_type`.

---

## 3. mempalace/mcp_server.py (vendored, mempalace 3.0+)

File: `.venv/lib/python3.12/site-packages/mempalace/mcp_server.py`

### 3.1 `_get_collection()` — lines 115-127

```python
def _get_collection(self):
    try:
        client = self._get_client()
        return client.get_collection("mempalace_drawers")
    except Exception:
        return None
```

**Impact:** `except Exception` swallows ALL exceptions including `KeyError`.
When `_type` is missing, the `KeyError` from configuration.py is caught here,
`None` is returned, and the user sees `{"error": "No palace found"}`.

---

## 4. Bridge scripts

### 4.1 `scripts/palace_format_detector.py` — line 237

```python
config.get("_type") == "CollectionConfigurationInternal"
```

Used as evidence for `CLASS_CHROMA_0_6` classification. A config without `_type`
would NOT match this, leading to classification as unknown/legacy format.

### 4.2 `scripts/check_palace_health.sh` — line 92

```python
broken = [
    (row[0], row[1])
    for row in rows
    if not json.loads(row[2] or "{}").get("_type")
]
```

Detects collections with missing `_type`. This script can repair the issue by
injecting the missing `_type` into `config_json_str`.

---

## 5. Cross-version comparison

### 5.1 ChromaDB 0.6.3 `config_json_str` (normal)

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

### 5.2 ChromaDB 1.5.7 `config_json_str`

```json
{}
```

**ChromaDB 1.5.7 stores an empty JSON object.** The entire configuration model
was rewritten:
- `ConfigurationInternal` class hierarchy → `CollectionConfiguration` TypedDict
- `_type` discriminator → removed entirely
- `hnsw_configuration` key → `hnsw` key (in new model)
- New: `spann`, `embedding_function` keys
- Loader: `load_collection_configuration_from_json_str()` in
  `chromadb/api/collection_configuration.py` (ignores `_type`)

### 5.3 Schema difference

| Column | 0.6.3 | 1.5.7 |
|--------|-------|-------|
| `id` | TEXT | TEXT |
| `name` | TEXT | TEXT |
| `dimension` | INTEGER | INTEGER |
| `database_id` | TEXT | TEXT |
| `config_json_str` | TEXT | TEXT |
| `schema_str` | — | TEXT |

---

## Summary

| Location | Role | Write/Read | Fails when missing? |
|----------|------|-----------|---------------------|
| `configuration.py:200` | Stamp class name | Write | N/A |
| `configuration.py:207` | Type guard | Read | Yes → enters error branch |
| `configuration.py:209` | Error message | Read | **Yes → KeyError (bug)** |
| `configuration.py:214` | Skip in iteration | Read | No (never reached) |
| `sysdb.py:886` | Deserialize config | Calls from_json_str | Propagates KeyError |
| `mcp_server.py:115` | Load collection | Calls get_collection | Swallows exception |
| `palace_format_detector.py:237` | Classify format | Read | No (returns False) |
| `check_palace_health.sh:92` | Detect broken configs | Read | No (detects it) |
