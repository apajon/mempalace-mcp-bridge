# Global Copilot Instructions (Repository-Wide)

These instructions are mandatory for every Copilot Chat interaction in this repository.

## MemPalace-first context policy

Before answering any repository-related question, proposing changes, or editing code, the agent must gather context in this order:

1. Query MemPalace project wing `mempalace_mcp_bridge` first.
2. Query shared wing(s) (for example `python`, `mcp`) second.
3. Merge results. A project entry overrides shared knowledge only when explicitly documented as a local override.
4. If MemPalace is unavailable, continue using this fallback chain without blocking the task:
   - `docs/architecture.md`
   - `README.md`
   - Workspace code/document search

## Mandatory behavior

- Do not skip MemPalace lookup for repository-context questions.
- If lookup is skipped or unavailable, explicitly state this and follow the fallback chain.
- Memory unavailability must never block user requests.
- For durable, repeatable, non-obvious findings, persist memory using project conventions.

## Source of truth

For detailed wing/room structure and persistence format, follow:
- `.github/instructions/mempalace-mcp-bridge.instructions.md`
