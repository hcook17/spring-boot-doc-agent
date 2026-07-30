# Root `skills/` mirror

**Start here for product skills:** [`adapters/claude/skills/`](../adapters/claude/skills/) (system of record).

Marketplace packaging uses `adapters/claude` (see `.claude-plugin/marketplace.json`). This root tree is a **synced mirror** of the product skills Cursor/local workflows may resolve without the adapter path:

- `document-spring-repo` (includes `references/`)
- `capacity-preflight`
- `citation-coverage`
- `semantic-pipeline-eval` (includes `references/`)

Adapter-only skills (`directional-tests`, `tool-quirks`) are **not** mirrored here.

Edit the adapter copy first, then sync here (or let CI's skill-SoT hash gate fail until they match). Do not diverge intentionally.
