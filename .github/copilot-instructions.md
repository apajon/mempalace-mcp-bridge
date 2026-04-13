# Global Copilot Instructions

For any repository-related question, proposal, debugging task, or code change, follow this process.

## Mandatory context retrieval

Before answering:

1. Query MemPalace project wing `mempalace_mcp_bridge`
2. Query shared wings relevant to the task, such as `python` and `mcp`
3. Merge results
   - project knowledge overrides shared knowledge only when explicitly documented as a local override
4. If MemPalace is unavailable, continue immediately with this fallback chain:
   - `docs/architecture.md`
   - `README.md`
   - workspace code and document search

Do not silently skip context retrieval.
Memory unavailability must never block the task.

## Mandatory response contract

For any repository-related response, begin with this block:

Context source:
