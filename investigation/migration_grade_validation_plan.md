# Migration-Grade Validation Plan

> Defines validation tiers, evidence standards, and honest status classification.
> Date: 2026-04-17

---

## Validation Tiers

### Tier 0: Cross-version incompatibility detection

**Question:** Can the system detect and explain a palace/runtime mismatch before the opaque failure occurs?

**How to test:**
```bash
<wrong-runtime-python> scripts/runtime_compat.py <palace-path>
```

**Pass criteria:** Exit code 1 with a message that names: the palace format, the runtime version, the specific failure mechanism (`KeyError: '_type'`), and an actionable recovery step.

**Status: PROVEN** — `runtime_compat.py` tested against all 4 combinations in the compatibility matrix.

---

### Tier 1: Storage reconstruction validity

**Question:** Does the reconstructed palace contain a valid SQLite database with the expected schema and collection structure?

**How to test:** Inspect `chroma.sqlite3` directly — check collections table exists, `config_json_str` is valid JSON, collection name matches.

**Pass criteria:** Schema matches native palace; `config_json_str` is consistent with the target runtime's format.

**Status: PROVEN** — Tier 1 of `compare_palaces.py` passes on 45-drawer rich fixture.

---

### Tier 2: Structural parity

**Question:** Does the reconstructed palace have the same drawer count and drawer IDs as the original?

**How to test:**
```bash
<target-python> scripts/investigation/compare_palaces.py <native> <reconstructed>
```

**Pass criteria:** Identical drawer count and identical set of drawer IDs.

**Status: PROVEN** — 45/45 drawers, 45/45 IDs match.

---

### Tier 3: Document content parity

**Question:** Are all documents byte-identical between native and reconstructed palaces?

**How to test:** Tier 3 of `compare_palaces.py`.

**Pass criteria:** Every document is identical. This includes Unicode, special characters, whitespace, and long content.

**Status: PROVEN** — 45/45 documents identical, including Japanese text, emoji, mathematical symbols, newlines/tabs, and a 5000-character document.

---

### Tier 4: Metadata parity

**Question:** Is all drawer metadata preserved through reconstruction, including varied types (strings, ints, floats)?

**How to test:** Tier 4 of `compare_palaces.py`.

**Pass criteria:** Every metadata record is identical.

**Status: PROVEN** — 45/45 metadata records identical, including `priority=1`, `confidence=0.95`, `char_count=5055`, `active="true"`.

---

### Tier 5: Embedding parity

**Question:** Are embeddings identical between native and reconstructed palaces?

**How to test:** Tier 5 of `compare_palaces.py`. Compares per-element with tolerance `1e-6`.

**Pass criteria:** `max_diff ≤ 1e-6` for all drawers.

**Status: PROVEN** — 45/45 embeddings match with `max_diff=0.00e+00` (exact match).

**Note:** Embeddings are exact because reconstruction exports and re-imports the same documents through the same embedding model. If the target runtime used a different embedding model, this tier would show differences — which would be expected and correct.

---

### Tier 6: Retrieval parity

**Question:** Do the same queries return the same results in the same order from both palaces?

**How to test:** Tier 6 of `compare_palaces.py` with 8 diverse queries covering all wings.

**Pass criteria:** Identical top-5 result IDs for all queries.

**Status: PROVEN** — 8/8 queries return identical top-5 in identical order.

**Test queries used:**
1. "database connection pooling"
2. "ROS 2 navigation behavior tree"
3. "Python type hints and dataclasses"
4. "Docker multi-stage build"
5. "emoji preservation in documents"
6. "virtual environment dependency management"
7. "authentication OIDC JWT"
8. "Git commit message conventions"

---

### Tier 7: Runtime loadability

**Question:** Can the target runtime's ChromaDB `PersistentClient` open the palace, access collections, and execute queries without error?

**How to test:** `runtime_load_test.py` (6-phase harness from the compatibility matrix study).

**Pass criteria:** All 5 phases pass (versions, raw_config, client_load, collection_access, query).

**Status: PROVEN** — Both native 1.x and reconstructed 1.x pass all 5 phases identically.

---

### Tier 8: MCP tool exposure

**Question:** Does the MCP server start successfully, register tools, and respond to tool calls when pointed at the reconstructed palace?

**How to test:**
```bash
MEMPALACE_PALACE_PATH=<reconstructed-palace> \
  <target-python> scripts/run_mcp_server_exploration.py
```
Then issue MCP tool calls over stdio.

**Pass criteria:** Server starts without error; tools are listed; at least one `mempalace_search` call returns expected results.

**Status: NOT YET TESTED** — The current evidence stops at ChromaDB API level. MCP stdio transport, tool registration, and tool invocation have not been validated on a reconstructed palace.

---

### Tier 9: Query usability (real workload)

**Question:** Can the palace serve realistic agent workflows — multi-turn queries, context retrieval, room/wing filtering?

**How to test:** Manual or scripted session using MCP tools with representative agent queries.

**Pass criteria:** Agent receives useful, relevant results comparable to native palace behavior.

**Status: NOT YET TESTED** — Requires MCP server to be running (Tier 8 first).

---

## Fixture Summary

### Minimal fixture (previous study)

- 3 drawers, 1 wing, 3 rooms
- Proved basic load/query parity
- Insufficient for migration confidence

### Rich fixture (current study)

- **45 drawers** across **5 wings** and **16 rooms**
- Content types: architecture decisions, conventions, debugging notes, ADRs, ROS 2 domain, Python/Docker/Git shared knowledge
- Edge cases: Japanese text, emoji, mathematical symbols, whitespace/newlines, 5000-char document, near-duplicate pair, varied metadata types (int, float, string, empty string)
- 8 diverse retrieval queries spanning all wings

---

## Honest Status Classification

### What is proven

1. **Reconstruction produces palaces that are structurally identical to natively created ones.**
   Tested on a 45-drawer fixture with 5 wings, 16 rooms, Unicode, varied metadata types, and long documents. All 6 comparison tiers pass with zero differences (Tiers 1-6).

2. **Reconstructed palaces load and query correctly in the intended 1.x runtime.**
   Tested via the runtime load harness (Tier 7). All 5 phases pass. Identical behavior to native 1.x palace.

3. **Cross-version mismatch is now detected and explained before the opaque failure.**
   `runtime_compat.diagnose()` identifies the 1.x→0.6.x mismatch with a precise message naming the mechanism (`KeyError: '_type'`), the root cause (format incompatibility), and recovery steps (Tier 0).

4. **The previously observed `_type` failure is a version mismatch, not a reconstruction defect.**
   Proven by the compatibility matrix: native 1.x palaces fail identically to reconstructed 1.x palaces when loaded in the 0.6.x runtime (Cases C vs D).

5. **ChromaDB 1.x is forward-compatible with 0.6.x palaces.**
   A native 0.6.x palace loads successfully in the 1.x runtime (Case F).

### What is not yet proven

1. **MCP server startup and tool exposure on reconstructed palaces.**
   Tiers 8-9 are not yet tested. The evidence stops at the ChromaDB API level. It is plausible that MCP-level issues (tool registration, stdio transport, mempalace internals) could introduce failures not visible at the database level.

2. **Large-scale reconstruction (hundreds/thousands of drawers).**
   The rich fixture has 45 drawers. A real production palace may have significantly more. Performance, memory pressure, and batch-import edge cases at scale are untested.

3. **Custom embedding function compatibility.**
   Both test environments use the default ChromaDB embedding function. If a palace was created with a custom embedding function, the 1.x format for `embedding_function` configuration might behave differently.

4. **Write-path behavior on reconstructed palaces.**
   All tests are read-only. Adding, updating, or deleting drawers in a reconstructed palace has not been tested.

5. **Reconstruction idempotency.**
   Running reconstruction twice on the same source has not been tested for consistency.

### What remains bounded and explicit

1. **The stable production path is unchanged.** `run.sh` still uses `.venv` (0.6.x). No regression risk.
2. **Incompatibilities are now detected, not silent.** Three layers of guards (version check, safety gate, runtime compat) prevent opaque failures.
3. **Reconstruction is experimental but evidence-based.** The experimental label is honest: Tiers 0-7 pass, Tiers 8-9 are open, and the constraints are documented.
4. **The next blocking question is specific:** Does MCP server startup work end-to-end on a reconstructed palace under the 1.x runtime?

---

## Next Experiments (Priority Order)

1. **Tier 8: MCP server startup test.** Start `run_mcp_server_exploration.py` against the reconstructed palace in the 1.x env, verify tool listing and a search query.

2. **Tier 9: Agent workflow simulation.** Use MCP tools to simulate a multi-turn agent session against the reconstructed palace.

3. **Scale test.** Create a fixture with 500+ drawers and run the full comparison.

4. **Write-path test.** Add drawers to a reconstructed palace, verify they persist and are queryable.
