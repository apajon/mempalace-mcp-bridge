# Experimental release strategy for the reconstruction workflow

## Recommended release status

**Classification: experimental release channel only.**

The reconstruction workflow is mature enough to expose to advanced evaluators, but not mature
enough to present as supported bridge functionality.

The right release posture is:

- **available**
- **explicitly opt-in**
- **kept outside the stable release path**
- **documented as experimental and unsupported**

## Release scope

### Included

- `scripts/palace_reconstruction_prototype.py`
- reconstruction bundle export/import flow
- structural validation
- retrieval validation
- usage comparison
- experimental MCP runtime validation
- dedicated reconstruction documentation

### Excluded

- any change to the stable `setup.sh` flow
- any change to `update.sh` that would install or enable ChromaDB `1.x`
- any change to `.mcp.json` generation for the stable path
- any change to `verify.sh` that would classify ChromaDB `1.x` as supported
- any automatic cutover or rollback logic
- any claim of supported `1.x` bridge operation

## Recommended exposure method

### Primary recommendation

Expose the workflow through a **separate experimental branch/tag** and a **documented manual
workflow**.

That means:

1. keep `main` and normal releases strictly on the stable `0.6.x` line
2. publish the reconstruction tooling only from a clearly named experimental branch/tag
3. require users to run the prototype script manually
4. require explicit target-runtime selection and manual validation review

### Why this is the safest approach

- it preserves the stable path completely
- it makes opt-in unambiguous
- it avoids implying that `setup.sh` or `.mcp.json` support ChromaDB `1.x`
- it matches the real maturity level of the workflow

### Exposure methods not recommended

- **stable release exposure** — too easy to misread as supported
- **automatic setup flag in stable scripts** — too easy to trigger accidentally
- **silent shipping without prominent docs** — hides the risks

## Opt-in model

The experimental release should require all of the following:

- checking out an experimental branch or release tag
- reading the reconstruction status/warnings first
- running the prototype script directly
- supplying explicit source and target paths
- performing validation before any manual switch

## Draft release notes

## Experimental release: reconstruction workflow preview

This release exposes an **experimental reconstruction workflow** for evaluating a non-destructive
migration from a stable ChromaDB `0.6.x` palace to a separate ChromaDB `1.x` target.

### What is included

- source export to a neutral reconstruction bundle
- target rebuild into a separate palace directory
- deterministic structural validation
- deterministic retrieval comparison
- deterministic usage comparison
- experimental MCP runtime validation

### What this is not

- not supported ChromaDB `1.x` bridge support
- not a supported upgrade path
- not an in-place migration tool
- not a one-command cutover flow
- not a production-readiness claim

### What we currently know

- the workflow can rebuild a separate target and validate it experimentally
- structural, retrieval, usage, and runtime checks are available
- stable `0.6.x` protections remain intact
- ChromaDB `1.x` runtime behavior is still not fully validated across palaces
- reconstructed `1.x` targets should still be treated as disposable evaluation artifacts

### Who should try this

- maintainers
- advanced users evaluating migration feasibility
- users comfortable with manual validation and rollback-by-path-switch

### Who should not try this

- users who need a supported install path
- users expecting stable ChromaDB `1.x` bridge behavior
- users who cannot preserve the original source palace during evaluation

### Required warnings

- keep the source palace untouched
- do not overwrite the stable palace path
- do not switch MCP/Copilot to the target without passing validation
- do not treat passing validation as production support
- do not assume one successful reconstruction generalizes to all palaces

## Usage instructions for the experimental release

1. Check out the experimental branch or tag.
2. Keep the stable source palace unchanged.
3. Use a separate target runtime and target directory.
4. Run the prototype manually:

```bash
python3 scripts/palace_reconstruction_prototype.py export \
  --source-palace ~/.mempalace/palace \
  --output-dir /tmp/palace-export

python3 scripts/palace_reconstruction_prototype.py import \
  --export-dir /tmp/palace-export \
  --target-palace /tmp/palace-target

python3 scripts/palace_reconstruction_prototype.py validate \
  --export-dir /tmp/palace-export \
  --target-palace /tmp/palace-target

python3 scripts/palace_reconstruction_prototype.py record-retrieval \
  --palace ~/.mempalace/palace \
  --queries-file /tmp/palace-export/reconstruction-retrieval-queries.json \
  --output /tmp/palace-export/source-retrieval-results.json \
  --label source

python3 scripts/palace_reconstruction_prototype.py record-retrieval \
  --palace /tmp/palace-target \
  --queries-file /tmp/palace-export/reconstruction-retrieval-queries.json \
  --output /tmp/palace-export/target-retrieval-results.json \
  --label target

python3 scripts/palace_reconstruction_prototype.py compare-retrieval \
  --source-results /tmp/palace-export/source-retrieval-results.json \
  --target-results /tmp/palace-export/target-retrieval-results.json
```

5. Optionally run usage comparison and experimental MCP runtime validation.
6. Only consider a manual switch if the target is acceptable for your own workload.

## README additions to ship with the experimental release

Recommended short additions:

- a distinct **Experimental release channel** section
- explicit statement that stable releases remain `0.6.x` only
- explicit statement that reconstruction is branch/tag-gated and manual
- link to the prototype and migration assessment docs

## Recommended branch and tag structure

### Branches

- `main` — stable bridge path, ChromaDB `0.6.x` only
- `explore/chromadb-1x-compat` — active development branch for reconstruction experiments
- optional future staging branch: `experimental/reconstruction`

### Tags

Use a clearly separate tag namespace for experimental releases:

- stable tags: `vX.Y.Z`
- experimental tags: `exp-reconstruction-vX.Y.Z`

This makes it difficult to confuse:

- stable product releases
- experimental reconstruction previews

## Final recommendation

If this workflow is exposed publicly, it should be exposed as:

- **experimental branch/tag only**
- **manual documented workflow**
- **unsupported for general bridge use**

It should **not** be shipped as part of the normal stable release story until ChromaDB `1.x`
runtime behavior is validated much more broadly.
