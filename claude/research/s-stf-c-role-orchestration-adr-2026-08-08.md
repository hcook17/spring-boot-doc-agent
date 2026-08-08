# ADR S-STF-C — Role orchestration (reject BMAD personas as control plane)

**Status:** Accepted · **Date:** 2026-08-08

**Decision:**

1. **Reject** BMAD full persona roster and MetaGPT virtual-company waterfall as the STF control plane.
2. **Implement** Planner→Executor→Reviewer with SPOQ-style topological waves + dual gates in `src/stf/graph` + `validators` + `runners`.
3. **Magentic ledger** fields on `TasksDocument.ledger` (`plan|progress|stall|reset|done`).
4. **In-house checkpoint** via `TasksStore.checkpoint()`; do **not** add `langgraph-checkpoint` until resume/crash tests prove need.
5. TraceDev-style Finding links (`path|test|mutant`) on ingest.

**Rationale:** arXiv SPOQ/Magentic/SLR/AI-SDLC protocol outweigh BMAD product packaging for this monorepo. Personas may exist as optional briefs later; never as SoR.

**Consequences:** Skills named frame/decompose/implement map to Planner/Executor; Reviewer is human/CI validation token (2+N SoD).
