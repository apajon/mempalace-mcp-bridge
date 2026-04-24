# Memory Engineering Extraction Audit

> **Status:** Audit only. No files are moved or rewritten by this document.
> **Target repo:** `mempalace-memory-engineering` (future, not yet created).
> **Source repo:** `mempalace-mcp-bridge` (this repo).
>
> **Purpose:** Classify every documentation and example asset in this repo into one of
> three buckets: **Keep**, **Move**, or **Reference only**, so a future split can be
> executed surgically without losing content or breaking cross-links.

---

## 1. Classification criteria

| Bucket             | Criterion                                                                                                                                                                                                             |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Keep**           | Tied to the concrete bridge: install, runtime, MCP wiring, VS Code, devcontainers, scripts, verification, ChromaDB 0.6.x ↔ 1.x migration pipeline, troubleshooting. Would make no sense outside this repo.            |
| **Move**           | General memory architecture / strategy / methodology. Describes *how to design and use* a governed memory layer regardless of the underlying bridge implementation. Reusable by any MCP client or any MemPalace user. |
| **Reference only** | Stays in the bridge repo but should be reduced to a short pointer to the memory-engineering repo once the split is done. Typically entry-point or index files.                                                        |

---

## 2. Classification table

| File                                                                                                                                     | Bucket             | Proposed destination in `mempalace-memory-engineering`            | Rationale                                                                                                                                                                                                                                                                                    |
| ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------ | ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `README.md`                                                                                                                              | **Reference only** | —                                                                 | Currently contains bridge usage **and** two links to memory strategy docs (`advanced_memory_strategy.md`, `memory_example.md`). Keep as bridge README, but after the split the two "Structured memory" bullets (lines ~180–181) should become links to the new repo. Do **not** rewrite now. |
| `docs/architecture.md`                                                                                                                   | **Keep**           | —                                                                 | Describes how *this bridge* sits between MemPalace, ChromaDB and MCP clients. Bridge-specific data-flow diagram. Not portable.                                                                                                                                                               |
| `docs/installation.md`                                                                                                                   | **Keep**           | —                                                                 | `uv`-based install for this repo.                                                                                                                                                                                                                                                            |
| `docs/mcp_vscode.md`                                                                                                                     | **Keep**           | —                                                                 | VS Code / Copilot Chat `.mcp.json` configuration for this bridge.                                                                                                                                                                                                                            |
| `docs/devcontainer_integration.md`                                                                                                       | **Keep**           | —                                                                 | Host↔container palace mount design, specific to running this bridge in a devcontainer.                                                                                                                                                                                                       |
| `docs/troubleshooting.md`                                                                                                                | **Keep**           | —                                                                 | `uv`, `mempalace`, MCP-server-specific failure modes. Bridge-scoped.                                                                                                                                                                                                                         |
| `docs/update_workflow.md`                                                                                                                | **Keep**           | —                                                                 | Documents `update.sh` and pinned ChromaDB `0.6.x` line. Bridge-scoped.                                                                                                                                                                                                                       |
| `docs/palace_format_detection.md`                                                                                                        | **Keep**           | —                                                                 | Detector for `chroma_0_6` vs `chroma_1_x` palace formats. Pipeline-internal.                                                                                                                                                                                                                 |
| `docs/cli_usage.md`                                                                                                                      | **Keep**           | —                                                                 | `scripts/reconstruct.sh` CLI reference. Bridge-scoped.                                                                                                                                                                                                                                       |
| `docs/error_model.md`                                                                                                                    | **Keep**           | —                                                                 | Error format of the reconstruction pipeline. Bridge-scoped.                                                                                                                                                                                                                                  |
| `docs/limitations.md`                                                                                                                    | **Keep**           | —                                                                 | Scope constraints of the reconstruction pipeline. Bridge-scoped.                                                                                                                                                                                                                             |
| `docs/support_matrix.md`                                                                                                                 | **Keep**           | —                                                                 | Tested ChromaDB / MemPalace / Python versions for the pipeline. Bridge-scoped.                                                                                                                                                                                                               |
| `docs/chromadb_v1_exploration.md`                                                                                                        | **Keep**           | —                                                                 | ChromaDB 1.x exploration notes for the migration work. Bridge-scoped. *Note:* contains one incidental mention of `advanced_memory_strategy.md` (line ~170) — verify during split; likely just a retrieval-demo reference, not a real dependency.                                             |
| `docs/chromadb_reconstruction_experimental_release.md`                                                                                   | **Keep**           | —                                                                 | Release notes for the experimental reconstruction branch. Bridge-scoped.                                                                                                                                                                                                                     |
| `docs/chromadb_reconstruction_migration.md`                                                                                              | **Keep**           | —                                                                 | Migration procedure for the reconstruction pipeline. Bridge-scoped.                                                                                                                                                                                                                          |
| `docs/chromadb_reconstruction_prototype.md`                                                                                              | **Keep**           | —                                                                 | Prototype design doc of the reconstruction pipeline. Bridge-scoped.                                                                                                                                                                                                                          |
| `docs/chromadb_reconstruction_workflow.md`                                                                                               | **Keep**           | —                                                                 | Operational workflow for running reconstruction. Bridge-scoped.                                                                                                                                                                                                                              |
| `docs/advanced_memory_strategy.md`                                                                                                       | **Move**           | `docs/strategy/advanced_memory_strategy.md`                       | The canonical long-form description of wings, rooms, retrieval order, persistence rules, and deduplication policy. Bridge-agnostic methodology; the document itself explicitly says it is "not the official workflow" of MemPalace and stands alone.                                         |
| `docs/memory_example.md`                                                                                                                 | **Move**           | `docs/strategy/memory_example.md`                                 | Concrete, tool-agnostic two-wing / three-room worked example. Already links upward to `advanced_memory_strategy.md`; belongs next to it.                                                                                                                                                     |
| `docs/deduplication.md`                                                                                                                  | **Move**           | `docs/strategy/deduplication.md`                                  | Compact reference for the deduplication policy described in `advanced_memory_strategy.md`. Purely methodological.                                                                                                                                                                            |
| `examples/ros2-architecture-context.instructions.md`                                                                                     | **Move**           | `examples/instructions/ros2-architecture-context.instructions.md` | Reusable `applyTo: "**"` agent instruction file. It is explicitly "a concrete instance of the pattern described in Advanced Memory Strategy" and has no ROS 2 *bridge* coupling beyond being a ROS 2 example of the methodology.                                                             |
| `examples/sample_notes/architecture_notes.md`                                                                                            | **Keep**           | —                                                                 | Fixture used to demo `mempalace mine` on this bridge. Small, concrete, tied to the bridge's "try it" flow. *Low-confidence — see §5.*                                                                                                                                                        |
| `examples/sample_notes/decisions.md`                                                                                                     | **Keep**           | —                                                                 | Same as above: mining fixture for the bridge demo. *Low-confidence — see §5.*                                                                                                                                                                                                                |
| `examples/sample_notes/ros2_debug.md`                                                                                                    | **Keep**           | —                                                                 | Same as above: mining fixture for the bridge demo. *Low-confidence — see §5.*                                                                                                                                                                                                                |
| `examples/mcp/vscode.mcp.json`                                                                                                           | **Keep**           | —                                                                 | VS Code MCP config template referencing this bridge.                                                                                                                                                                                                                                         |
| `examples/mcp/copilot_mcp_example.json`                                                                                                  | **Keep**           | —                                                                 | Generic MCP stdio config template referencing this bridge.                                                                                                                                                                                                                                   |
| `.github/instructions/mempalace-mcp-bridge.instructions.md`                                                                              | **Keep**           | —                                                                 | Copilot instructions scoped to this repository. *After split,* its link to `docs/advanced_memory_strategy.md` becomes a cross-repo reference — update as part of the migration, not now.                                                                                                     |
| `investigation/**`                                                                                                                       | **Keep**           | —                                                                 | Engineering notes / JSON artifacts for the ChromaDB 1.x reconstruction effort. Entirely bridge-internal.                                                                                                                                                                                     |
| `scripts/**`, `tests/**`, `run.sh`, `setup.sh`, `update.sh`, `verify.sh`, `mempalace.yaml`, `pyproject.toml`, `uv.lock`, `entities.json` | **Keep**           | —                                                                 | Executable bridge itself; out of scope for the memory-engineering repo.                                                                                                                                                                                                                      |

---

## 3. Summary by bucket

### 3.1 Move to `mempalace-memory-engineering`

- `docs/advanced_memory_strategy.md` → `docs/strategy/advanced_memory_strategy.md`
- `docs/memory_example.md` → `docs/strategy/memory_example.md`
- `docs/deduplication.md` → `docs/strategy/deduplication.md`
- `examples/ros2-architecture-context.instructions.md` → `examples/instructions/ros2-architecture-context.instructions.md`

These four files form a self-contained, bridge-agnostic unit: one long-form strategy, one worked example, one compact deduplication reference, and one concrete agent instruction file that applies the pattern.

### 3.2 Reference only (stay, but will need a short pointer after the split)

- `README.md` — lines ~180–181 currently link directly to `docs/advanced_memory_strategy.md` and `docs/memory_example.md`. After the split, replace those two bullets with a single pointer to the memory-engineering repo. Not part of this audit.

### 3.3 Keep in `mempalace-mcp-bridge`

Everything else (see table).

---

## 4. Cross-links that will need updating when the split happens

> Flagged now so nothing is silently broken during the split. **Do not edit these yet.**

| File (stays in bridge)                                      | Current link                                                               | Action after split                                                                |
| ----------------------------------------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `README.md`                                                 | `docs/advanced_memory_strategy.md`, `docs/memory_example.md`               | Replace with links to the new repo.                                               |
| `.github/instructions/mempalace-mcp-bridge.instructions.md` | `../../docs/advanced_memory_strategy.md`                                   | Replace with a link to the new repo, or drop if the instruction file is reworked. |
| `docs/chromadb_v1_exploration.md` (line ~170)               | Incidental mention of `advanced_memory_strategy.md` as a retrieval example | Verify context; likely rewrite to a neutral placeholder or link to new repo.      |

| File (moves to memory-engineering)                   | Current internal link                                                                    | Action after split                                                                     |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `docs/advanced_memory_strategy.md`                   | `deduplication.md`                                                                       | Link remains valid if all three move together into `docs/strategy/`.                   |
| `docs/deduplication.md`                              | `advanced_memory_strategy.md`, `memory_example.md`                                       | Same — remains valid if co-located.                                                    |
| `docs/memory_example.md`                             | `advanced_memory_strategy.md`, `deduplication.md`                                        | Same.                                                                                  |
| `examples/ros2-architecture-context.instructions.md` | `../docs/advanced_memory_strategy.md`, `docs/deduplication.md`, `docs/memory_example.md` | Paths must be rewritten relative to the new repo layout (e.g. `../docs/strategy/...`). |

---

## 5. Uncertainty / judgment calls

These classifications are **not obviously** right. Flagging explicitly so a reviewer can push back.

1. **`examples/sample_notes/*.md`** — classified **Keep**.
   These files look like generic mining fixtures. An argument exists for moving them to the memory-engineering repo as part of a pedagogical "how to mine content" example. I kept them in the bridge because:
   - they are the most natural target for a bridge-side "try it now" walkthrough,
   - they are small and cheap to duplicate later if the memory-engineering repo wants its own fixtures.
   **Reviewer input welcome.**

2. **`examples/ros2-architecture-context.instructions.md`** — classified **Move**.
   It is ROS 2-flavored, which could suggest it belongs in a ROS 2-specific repo rather than a generic memory-engineering repo. I still classified it as **Move** because its entire point is to demonstrate the wings/rooms/retrieval-priority pattern; ROS 2 is only the illustrative domain. If the target repo wants strict domain-neutrality, this file could instead be genericized in-place and then moved, or split into a generic template + ROS 2 example.

3. **`docs/chromadb_v1_exploration.md`** — classified **Keep**.
   Contains one mention of `advanced_memory_strategy.md`. I treated this as incidental (used as an example retrieval target, not as a dependency). Worth a 30-second re-read during the actual split to confirm.

4. **`.github/instructions/mempalace-mcp-bridge.instructions.md`** — classified **Keep**.
   It is repo-scoped Copilot guidance, so it belongs here. But its retrieval-order / persistence / deduplication prose is essentially a condensed copy of the strategy docs. Once those move, this file should ideally shrink to bridge-specific bits + a link to the new repo. Out of scope for this audit.

5. **README.md** — classified **Reference only** rather than **Keep** on purpose.
   The README's current job is bridge-first, so it physically stays. The "Reference only" label flags that *part of its content* will need to become a link after the split. Not a move.

---

## 6. What this audit explicitly does *not* do

- Does not move any files.
- Does not rewrite the README.
- Does not delete or edit any content.
- Does not create the target repo.
- Does not update cross-links (only lists them).

All of the above are deliberate per the task constraints.
