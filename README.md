# MemPalace MCP Bridge — Safe, Non-Destructive Migration to ChromaDB 1.x

---

## What this is

A safe and explicit way to:

- run MemPalace reliably today (0.6.x)
- reconstruct a palace into a ChromaDB 1.x target
- verify that the result actually works at runtime (MCP)

---

## Why this exists

MemPalace is powerful, but real-world usage quickly hits two issues:

- setup friction (manual installs, fragile configs)
- **no safe migration path to newer ChromaDB versions**

Typical approaches:
- copy data blindly
- assume runtime compatibility
- validate only structure

This leads to:
- runtime failures
- misleading “success”
- hard-to-debug inconsistencies

👉 A palace can look valid… and still be unusable.

This project fixes that.

> It turns MemPalace migration into a **controlled, explicit, and verifiable process**.

---

## Core guarantee

This system enforces a strict invariant:

- a migration either **succeeds and is validated**
- or **fails explicitly**

**No silent corruption. No ambiguous state.**

---

## What you actually get

- non-destructive reconstruction (source is never modified)
- rebuilt 1.x palace target
- runtime compatibility checks
- structured, actionable errors
- validation at multiple levels:
  - structure
  - retrieval
  - **real MCP runtime**

---

## What this project provides

### 1. Stable usage (0.6.x path)
- reproducible environment
- predictable behavior
- no hidden assumptions

### 2. Safe reconstruction (1.x path)
- source-preserving
- explicit pipeline
- validation at each stage

### 3. Runtime compatibility detection
- prevents mixing incompatible stacks (0.6.x vs 1.x)
- eliminates misleading errors

### 4. Validation tooling
- structural checks
- retrieval checks
- **MCP runtime validation (server + tools + queries)**

👉 The goal is simple:

**Not just “data looks correct” — but “the system actually works”.**

---

## Migration guarantees (tested scope)

- non-destructive behavior
- no silent corruption
- explicit failure model
- runtime-valid reconstruction

Reconstructed 1.x palaces have been validated against native 1.x:

- same MCP tools exposed
- same queries
- same results
- no semantic differences observed

---

## What makes this different

Most migration tools ask:

> “Did the data transfer succeed?”

This project asks:

> **“Does the system still behave correctly at runtime?”**

Key differences:

- runtime-level validation (not just storage)
- adversarial testing (not just happy path)
- explicit failure boundaries
- no silent corruption

---

## Recommended workflow

1. Stay on 0.6.x if you need stability today
2. Reconstruct to 1.x using this pipeline
3. Validate:
   - structure
   - retrieval
   - runtime (MCP)
4. Only use reconstructed palaces after validation
5. If it fails → read the error, don’t guess

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/apajon/mempalace-mcp-bridge.git
cd mempalace-mcp-bridge

# 2. Setup
./scripts/setup.sh

# 3. Reconstruct
python scripts/palace_reconstruction_prototype.py \
  --source /path/to/source_palace \
  --target /path/to/reconstructed_palace

# 4. Validate runtime
python scripts/investigation/runtime_load_test.py \
  /path/to/reconstructed_palace
````

---

## Documentation

The documentation is organized by purpose:

### Core system

* Architecture overview: [docs/architecture.md](docs/architecture.md)
* Error model: [docs/error_model.md](docs/error_model.md)
* Support matrix: [docs/support_matrix.md](docs/support_matrix.md)
* Limitations: [docs/limitations.md](docs/limitations.md)

### Usage & workflows

* CLI usage: [docs/cli_usage.md](docs/cli_usage.md)
* Update and verify workflow: [docs/update_workflow.md](docs/update_workflow.md)
* Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)

### Advanced topics

* Structured memory patterns: [docs/advanced_memory_strategy.md](docs/advanced_memory_strategy.md)
* Structured memory example: [docs/memory_example.md](docs/memory_example.md)
* Palace format detection: [docs/palace_format_detection.md](docs/palace_format_detection.md)

### Integration

* VS Code / MCP: [docs/mcp_vscode.md](docs/mcp_vscode.md)
* Devcontainer integration: [docs/devcontainer_integration.md](docs/devcontainer_integration.md)

---

## What is NOT guaranteed

This project is intentionally bounded.

It does NOT claim:

* universal compatibility with all MemPalace history
* correctness on all real-world datasets
* automatic repair of corrupted sources

Unsupported / rejected inputs include:

* corrupted SQLite databases
* inconsistent metadata
* duplicated identifiers
* structurally incoherent palaces

👉 These cases are **rejected explicitly**, never silently accepted.

---

## Limitations

* bounded to tested MemPalace / ChromaDB versions
* assumes internally consistent source semantics
* does not attempt data repair

---

## Project status

This project provides:

* a non-destructive reconstruction pipeline
* runtime-valid 1.x targets (within tested scope)
* explicit failure handling
* zero silent corruption in tested adversarial cases

It is not an experiment anymore.
It is not a universal migration solution either.

👉 It is a **safe, bounded, technically verified migration path**.

---

## Philosophy

* Fail explicitly
* Never guess
* Validate behavior, not just structure
* Prefer safety over convenience

---

## Related

* MemPalace: [https://github.com/milla-jovovich/mempalace](https://github.com/milla-jovovich/mempalace)
* ChromaDB: [https://github.com/chroma-core/chroma](https://github.com/chroma-core/chroma)

---

If something fails, it should fail clearly.
If something works, it should work for the right reasons.
