# ChromaDB 1.x compatibility exploration

## Status

**Conclusion: partially viable.**

ChromaDB 1.x is **not supportable by this repo as-is** because the bridge intentionally hard-blocks anything outside `0.6.x` in setup, update, verify, manifesting, and the guarded MCP launcher.

At the same time, an isolated exploration environment **did work at runtime** with:

- `chromadb==1.5.7`
- `mempalace==3.3.0`
- a fresh palace
- a copied bridge-created legacy palace from the current `0.6.3` environment

That means the main blockers are currently **repo-local policy and tooling**, not a confirmed blanket runtime incompatibility with ChromaDB 1.x.

---

## Scope and assumptions

This exploration was run on a local branch (`explore/chromadb-1x-compat`) and intentionally did **not** relax stable `0.6.x` protections in the normal bridge path.

Assumptions used here:

1. `main` remains the stable `chromadb>=0.6,<0.7` line.
2. ChromaDB 1.x testing must happen in a side-by-side environment.
3. A copied current palace is a useful legacy probe, but it is **not** evidence for very old pre-`0.6` palaces.

Tested environments:

| Environment | Result |
|---|---|
| Stable repo baseline | `.venv` with `mempalace==3.1.0`, `chromadb==0.6.3` |
| Exploration runtime | `.venv-chromadb1` with `mempalace==3.3.0`, `chromadb==1.5.7` |

---

## Repo inspection summary

The current bridge bakes in `0.6.x` assumptions in multiple layers:

| Surface | Current behavior | Classification |
|---|---|---|
| `pyproject.toml` | Declares `chromadb>=0.6,<0.7` | repo-local policy |
| `scripts/bootstrap.sh` | Installs `mempalace>=3.0.0` with `chromadb>=0.6,<0.7` | repo-local policy |
| `update.sh` | Reinstalls the same pinned line and re-checks it | repo-local policy |
| `scripts/check_chromadb_version.py` | Rejects anything outside `0.6.x` | repo-local policy |
| `scripts/run_mcp_server.py` | Calls the version guard before starting MCP | repo-local policy |
| `verify.sh` | Marks non-`0.6.x` installs as unsupported/unsafe | repo-local policy |
| `scripts/palace_manifest.py` | Hardcodes `compatibility_line = "chromadb-0.6.x"` | repo-local policy |
| `verify.sh` manifest checks | Treat manifest Chroma metadata outside `0.6.x` as fatal | repo-local policy |
| lifecycle scripts | Hardcode `.venv/bin/python` | repo-local testing friction |
| `scripts/check_palace_health.sh` | Uses the active Chroma runtime against palace storage | actual runtime probe |

Baseline verification on the stable environment was healthy:

```text
Result: SUPPORTED and healthy
12 checks passed.
```

---

## Proposed exploration plan

1. Keep the stable `.venv` and default palace untouched.
2. Create a side-by-side `.venv-chromadb1`.
3. Use separate palace roots:
   - `fresh-palace` for new-storage behavior
   - `legacy-palace` as a copy of the existing bridge-created `0.6.3` palace
4. Test four things independently:
   - install/resolve
   - fresh init + mining + search
   - legacy search + additional mining
   - MCP startup through the raw MemPalace server vs the repo's guarded launcher
5. Keep confirmed facts separate from hypotheses.

---

## Minimal code changes needed to test cleanly

The smallest safe exploration changes are:

1. **Add an exploration-only MCP launcher** that skips the stable Chroma guard.  
   Added here as `scripts/run_mcp_server_exploration.py`.
2. **Do not change** `setup.sh`, `update.sh`, `verify.sh`, `scripts/check_chromadb_version.py`, or `scripts/run_mcp_server.py`. Those are the stable protections.
3. For broader repeatable exploration, the next safe improvement would be an **opt-in alternate Python path override** for lifecycle scripts, because current scripts hardcode `.venv/bin/python` and make side-by-side testing manual.

I did **not** weaken the stable path in this branch.

---

## Confirmed facts

### 1. Current repo setup cannot complete on ChromaDB 1.x as-is

Confirmed from code inspection:

- `pyproject.toml` pins `chromadb>=0.6,<0.7`
- `scripts/bootstrap.sh` installs the same pin
- `update.sh` reinstalls the same pin
- `scripts/check_chromadb_version.py` rejects non-`0.6.x`

So the bridge's normal setup/update path is **blocked by local policy before runtime compatibility is even tested**.

### 2. ChromaDB 1.x install resolution succeeds in an isolated environment

Command outcome:

```bash
uv venv .venv-chromadb1 --python 3.12
uv pip install --python .venv-chromadb1/bin/python "mempalace>=3.0.0" "chromadb>=1,<2"
```

Resolved versions:

- `mempalace==3.3.0`
- `chromadb==1.5.7`

Important nuance:

- the stable `.venv` had `mempalace==3.1.0`
- `mempalace==3.1.0` cannot be installed with ChromaDB 1.x because it declares `chromadb<0.7`
- so a ChromaDB 1.x exploration is also a **MemPalace version change**

This is a real compatibility caveat, not just a packaging detail.

### 3. Fresh palace creation works on the isolated ChromaDB 1.x stack

Confirmed with:

```bash
MEMPALACE_PALACE_PATH=<fresh-palace> .venv-chromadb1/bin/mempalace init .
```

Observed behavior:

- `init` completed successfully
- `init` was interactive and required accepting detected entities/rooms
- `init` wrote `entities.json` and `mempalace.yaml` in the repo root

This is **not** a ChromaDB failure, but it is relevant exploration friction.

### 4. Mining/indexing works on a fresh palace under ChromaDB 1.x

Confirmed with:

```bash
MEMPALACE_PALACE_PATH=<fresh-palace> .venv-chromadb1/bin/mempalace mine .
```

Observed result:

- exit status `0`
- `34` files processed
- `234` drawers filed

### 5. Retrieval/search works on a fresh palace under ChromaDB 1.x

Confirmed with:

```bash
MEMPALACE_PALACE_PATH=<fresh-palace> .venv-chromadb1/bin/mempalace search "architecture decisions"
```

Observed result:

- exit status `0`
- normal ranked results returned from `advanced_memory_strategy.md`

### 6. A copied current legacy palace also worked under ChromaDB 1.x

Tested palace:

- a copy of the current bridge-managed palace from the stable environment
- stable manifest/environment showed `chromadb==0.6.3`

Confirmed with:

```bash
MEMPALACE_PALACE_PATH=<legacy-palace> .venv-chromadb1/bin/mempalace search "architecture decisions"
MEMPALACE_PALACE_PATH=<legacy-palace> .venv-chromadb1/bin/mempalace mine .
```

Observed result:

- search exit status `0`
- mining exit status `0`

So the tested `0.6.3` palace did **not** show a ChromaDB 1.x runtime break in this exploration.

### 7. MCP startup is blocked by the repo launcher but not by raw MemPalace

Repo launcher under the isolated 1.x environment:

```bash
MEMPALACE_PALACE_PATH=<fresh-palace> .venv-chromadb1/bin/python scripts/run_mcp_server.py
```

Observed result:

```text
[ERROR] unsupported chromadb 1.5.7. This stable branch supports 0.6.x only. Run: bash update.sh
```

Direct MemPalace server:

```bash
MEMPALACE_PALACE_PATH=<fresh-palace> .venv-chromadb1/bin/python -m mempalace.mcp_server
MEMPALACE_PALACE_PATH=<legacy-palace> .venv-chromadb1/bin/python -m mempalace.mcp_server
```

Observed result:

- both printed `MemPalace MCP Server starting...`
- both stayed alive past the observation window

That is strong evidence that the immediate MCP startup blocker is **repo-local**, not a confirmed ChromaDB 1.x runtime failure.

---

## Compatibility matrix

| Capability | Current repo behavior | Isolated 1.x probe | Evidence quality | Main blocker |
|---|---|---|---|---|
| Setup completes with ChromaDB 1.x | **No** | **Yes** | confirmed | repo pins + version guard |
| Fresh palace can be created | **Not through current stable scripts** | **Yes** | confirmed | repo pinning; upstream init is interactive |
| MCP starts successfully | **No** via `scripts/run_mcp_server.py` | **Yes** via raw `mempalace.mcp_server` | confirmed | repo guarded launcher |
| Mining/indexing works | **Not reachable through current stable 1.x path** | **Yes** on fresh and copied legacy palace | confirmed | repo pinning/venv assumptions |
| Retrieval/search works | **Not reachable through current stable 1.x path** | **Yes** on fresh and copied legacy palace | confirmed | repo pinning/venv assumptions |
| Copied current legacy palace survives 1.x runtime | **N/A in stable path** | **Yes** | confirmed | none observed |
| Very old pre-0.6 palaces survive 1.x runtime | **Unknown** | **Unknown** | unconfirmed | not tested here |
| Bridge verify/manifest flow recognizes 1.x as supported | **No** | **No** | confirmed | repo-local policy |

---

## Fresh vs old palace breakage

### Confirmed

- The bridge's current blockers are **not tied to palace age**.  
  Setup, verify, manifest checks, and the guarded MCP launcher reject ChromaDB 1.x before fresh-vs-legacy matters.
- In the isolated runtime probe, **both**:
  - a fresh palace, and
  - a copied bridge-created `0.6.3` palace
  
  worked for search, mining, and raw MCP startup.

### Not confirmed

- Whether **older pre-0.6 palaces** still fail on ChromaDB 1.x.
- Whether specific historical palace formats trigger the `mismatched types` storage error documented in `docs/troubleshooting.md`.

So the currently confirmed failures are **repo-local**, while the historical old-palace breakage remains an **upstream hypothesis / known risk**, not a reproduced fact from this run.

---

## Local vs upstream attribution

### Local to this repo

- `0.6.x` pinning in dependency declarations and lifecycle scripts
- explicit runtime version rejection
- manifest compatibility metadata fixed to `chromadb-0.6.x`
- verify classifying 1.x as unsupported
- hardcoded `.venv` paths that make side-by-side testing awkward

### Upstream MemPalace / ChromaDB behavior observed here

- `mempalace>=3.0.0` with ChromaDB 1.x resolves to a newer MemPalace (`3.3.0`)
- fresh init is interactive
- fresh init writes repo-root config/artifact files
- mining/search/raw MCP startup all worked on the tested stack
- `onnxruntime` emitted GPU discovery warnings, but they were non-fatal

### Upstream risk not yet reproduced here

- failures on substantially older palaces
- failures on mixed-format or partially migrated palace storage

---

## Blockers to claiming support

The repo should **not** claim ChromaDB 1.x support yet because:

1. the stable path still intentionally blocks it everywhere
2. the tested working path required a newer MemPalace (`3.3.0`)
3. very old palace compatibility is still unproven
4. verify/manifest/reporting logic still encode `0.6.x` as the only supported line

---

## Recommended next step for this exploration branch

If exploration continues, the next safe move is:

1. keep stable protections unchanged
2. add opt-in exploration helpers only
3. test at least one known older pre-`0.6` palace snapshot
4. decide whether ChromaDB 1.x support would mean:
   - "new palaces only"
   - "new palaces + selected migrated `0.6.x` palaces"
   - or "blocked until older-palace migration is understood"

---

## Final assessment

**Partially viable.**

ChromaDB 1.x is **not viable in the repo's current supported path**, but it **is viable enough in isolated runtime probes** that the work appears worth continuing on an exploration branch.

The present blockers are mostly **local guardrails and support policy**, plus one important upstream dependency shift to newer MemPalace. The remaining unknown is whether substantially older palaces fail in ways that would still block practical support.
