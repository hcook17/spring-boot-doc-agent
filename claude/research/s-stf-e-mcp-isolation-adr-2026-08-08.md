# ADR S-STF-E — MCP / tool isolation for implement agents

**Status:** Accepted · **Date:** 2026-08-08

**Decision:** Server-derived filesystem root only (`DOC_ENGINE_ROOT` / `DOC_ENGINE_RUN_DIR`). MCP and `dispatch_tool` must not accept caller `root`. Agent briefs must not invent absolute paths. 2+N SoD: Implement cannot mark DONE without Reviewer `validation_token`.

**Rationale:** arXiv MCP threat papers + PR #94 C1 confused-deputy findings. Aligns with MCP filesystem Roots pattern.

**Consequences:** Query surface E-Q0 is a hard dependency for any STF implement wave that reads Stage-0 artifacts via MCP.
