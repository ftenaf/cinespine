## Code Navigation & Search Preferences

**CRITICAL RULE:**
Always prioritize using `codegraph` (`codegraph_explore` MCP tool or `codegraph` CLI) and `graphify` (e.g. `graphify query`) over standard `grep_search` or basic shell commands (`grep`, `find`) for codebase navigation, symbol discovery, and structural analysis.

1. **CodeGraph:** Use `.codegraph/` (via MCP `codegraph_explore`) for jumping directly to symbol definitions and viewing call paths.
2. **Graphify:** Use `graphify-out/` (via MCP or CLI) to understand architectural concepts, file relationships, and complex context.
3. **Fallback Only:** Use `grep_search` ONLY if the advanced tools fail, if the specific directory is not indexed, or if searching for simple string literals that are not code symbols.
