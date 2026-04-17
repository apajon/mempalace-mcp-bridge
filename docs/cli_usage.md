# CLI Usage

## Quick Start

The recommended way to run the full migration is through the shell wrapper:

```bash
./scripts/reconstruct.sh \
  --source-palace ~/.mempalace \
  --target-palace ~/mempalace-v1 \
  --work-dir /tmp/reconstruction-run \
  --source-python .venv/bin/python \
  --target-python .venv-chromadb1/bin/python
```

This runs the complete pipeline: export → import → validate → retrieval recording → retrieval comparison.

## Shell Wrapper (`reconstruct.sh`)

### Required Arguments

| Flag | Description |
|------|-------------|
| `--source-palace PATH` | Source palace to export from (must be `chroma_0_6` format) |
| `--target-palace PATH` | Fresh target palace directory to create |
| `--work-dir PATH` | Working directory for export bundle and artifacts |

### Optional Arguments

| Flag | Default | Description |
|------|---------|-------------|
| `--source-python PATH` | `.venv/bin/python` | Python executable for the source 0.6.x runtime |
| `--target-python PATH` | `.venv/bin/python` | Python executable for the target 1.x runtime |
| `--with-usage` | off | Also run usage scenario recording and comparison |
| `--with-mcp-runtime` | off | Also run MCP runtime validation |
| `--mcp-launcher-script PATH` | `scripts/run_mcp_server_exploration.py` | MCP launcher script (with `--with-mcp-runtime`) |
| `--dry-run` | off | Print the pipeline steps without executing them |
| `--debug` | off | Pass `--debug` to the Python script for full tracebacks |

### Pipeline Steps

The wrapper executes these steps in order:

1. **Export** — extract drawers from source palace into a neutral JSON bundle
2. **Import** — load the bundle into a fresh target palace via the target runtime
3. **Validate** — compare target palace structure against the export manifest
4. **Record source retrieval** — run deterministic queries against the source
5. **Record target retrieval** — run the same queries against the target
6. **Compare retrieval** — verify result overlap meets thresholds

With `--with-usage`, three additional steps run usage scenario validation.
With `--with-mcp-runtime`, one additional step probes MCP tool availability.

### Example: Dry Run

```bash
./scripts/reconstruct.sh \
  --source-palace ~/.mempalace \
  --target-palace ~/mempalace-v1 \
  --work-dir /tmp/recon \
  --dry-run
```

### Example: Full Pipeline with Debug

```bash
./scripts/reconstruct.sh \
  --source-palace ~/.mempalace \
  --target-palace ~/mempalace-v1 \
  --work-dir /tmp/recon \
  --source-python .venv/bin/python \
  --target-python .venv-chromadb1/bin/python \
  --with-usage \
  --debug
```

## Python Script Direct Usage

The Python script can also be invoked directly for individual steps.
All subcommands support `--json` for machine-readable output.

### Global Flag

| Flag | Description |
|------|-------------|
| `--debug` | Show full Python tracebacks on failure |

### Subcommands

#### `export`

Extract drawers from a source palace into an export bundle.

```bash
python scripts/palace_reconstruction_prototype.py export \
  --source-palace ~/.mempalace \
  --output-dir /tmp/recon/export
```

#### `import`

Import an export bundle into a fresh target palace.

```bash
python scripts/palace_reconstruction_prototype.py import \
  --export-dir /tmp/recon/export \
  --target-palace ~/mempalace-v1
```

#### `validate`

Compare a rebuilt target against the export manifest.

```bash
python scripts/palace_reconstruction_prototype.py validate \
  --export-dir /tmp/recon/export \
  --target-palace ~/mempalace-v1
```

#### `record-retrieval`

Run deterministic retrieval queries against a palace and save results.

```bash
python scripts/palace_reconstruction_prototype.py record-retrieval \
  --palace ~/.mempalace \
  --queries-file /tmp/recon/export/reconstruction-retrieval-queries.json \
  --output /tmp/recon/source-retrieval.json \
  --label source
```

#### `compare-retrieval`

Compare source and target retrieval results.

```bash
python scripts/palace_reconstruction_prototype.py compare-retrieval \
  --source-results /tmp/recon/source-retrieval.json \
  --target-results /tmp/recon/target-retrieval.json
```

Optional tolerance flags: `--count-tolerance N` (default: 1), `--min-overlap-ratio F` (default: 0.4).

#### `record-usage`

Run usage scenarios against a palace and save results.

```bash
python scripts/palace_reconstruction_prototype.py record-usage \
  --palace ~/.mempalace \
  --scenarios-file /tmp/recon/export/reconstruction-usage-scenarios.json \
  --output /tmp/recon/source-usage.json \
  --label source
```

#### `compare-usage`

Compare source and target usage results.

```bash
python scripts/palace_reconstruction_prototype.py compare-usage \
  --source-results /tmp/recon/source-usage.json \
  --target-results /tmp/recon/target-usage.json
```

Optional tolerance flags: `--count-tolerance N` (default: 1), `--min-overlap-ratio F` (default: 0.4).

#### `validate-mcp-runtime`

Probe MCP server startup and tool availability against a palace.

```bash
python scripts/palace_reconstruction_prototype.py validate-mcp-runtime \
  --export-dir /tmp/recon/export \
  --palace ~/mempalace-v1 \
  --python .venv-chromadb1/bin/python \
  --launcher-script scripts/run_mcp_server_exploration.py
```

## Output Modes

- **Human mode** (default): Formatted text with `[OK]`, `[INFO]`, `[ERROR]` prefixes
- **JSON mode** (`--json`): Machine-readable JSON on stdout; errors still go to stderr
- **Debug mode** (`--debug`): Full Python tracebacks on failure

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Pipeline failure (check stderr for details) |

## Related

- [Error model](error_model.md) — how failures are reported
- [Support matrix](support_matrix.md) — tested input classes
- [Limitations](limitations.md) — known boundaries
