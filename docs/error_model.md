# Error Model

All failures in the reconstruction pipeline are surfaced through a structured error format.
No raw Python tracebacks are shown in normal operation.

## Error Format

Every CLI failure prints:

```
[ERROR] <Stage> failed: <summary>
[INFO]  Category: <category>
[INFO]  Details:
[INFO]    - <detail line>
[INFO]  Where to look:
[INFO]    - <file or path>
[INFO]  Suggested action: <what to do>
```

## Fields

| Field | Description |
|-------|-------------|
| **Stage** | Pipeline phase where the failure occurred: `export`, `import`, `validate`, `retrieval recording`, `usage recording` |
| **Category** | Error class: `structural` (missing/corrupt files, wrong format) or `data integrity` (invalid content, duplicate IDs) |
| **Summary** | One-line description of the failure |
| **Details** | Specific diagnostic information (file paths, counts, IDs) |
| **Where to look** | File paths relevant to the failure |
| **Suggested action** | Actionable next step for the operator |

## Modes

### Normal mode (default)

Concise structured error. No traceback. Example:

```
[ERROR] Export failed: source palace database query failed: file is not a database
[INFO]  Category: structural
[INFO]  Details:
[INFO]    - sqlite path: /path/to/palace/chroma.sqlite3
[INFO]  Where to look:
[INFO]    - /path/to/palace/chroma.sqlite3
[INFO]  Suggested action: The database file may be corrupted or not a valid SQLite database. Verify the file integrity.
```

### Debug mode (`--debug`)

Full Python traceback is printed instead of the structured format.
Use this when filing bug reports or diagnosing unexpected behavior.

```bash
python scripts/palace_reconstruction_prototype.py --debug export --source-palace /path/to/palace --output-dir /path/to/output
```

Or through the shell wrapper:

```bash
./scripts/reconstruct.sh --debug --source-palace ... --target-palace ... --work-dir ...
```

## Error Categories

### Structural errors

Raised when the pipeline cannot proceed due to missing, corrupt, or incompatible files:

- Source palace not classified as `chroma_0_6`
- Missing `chroma.sqlite3`
- Corrupted SQLite database
- Wrong database schema
- Output directory already exists
- Target path conflicts
- Invalid export bundle format

### Data integrity errors

Raised when the source data violates constraints required for safe reconstruction:

- Duplicate embedding IDs
- Blank or null IDs
- Missing or duplicate `chroma:document` entries
- Duplicate metadata keys
- Empty drawer set
- Bundle integrity check failures

### Runtime errors

Raised for issues during import or validation against the target runtime:

- Collection creation failure
- Batch import rejection
- Manifest format violations

## Exception Hierarchy

```
Exception
├── ReconstructionCliError (RuntimeError)
│   ├── stage, category, summary, details
│   ├── where_to_look, suggested_action
│   └── → structured CLI output in normal mode
├── RuntimeError (manifest/bundle validation)
│   └── → single-line [ERROR] + hint to use --debug
└── Other exceptions
    └── → "Unexpected failure" + hint to use --debug
```

## Guarantees

- No raw traceback in normal mode
- All known failure paths produce actionable messages
- Debug mode preserves full engineering context
- Exit code is always `1` on failure, `0` on success
