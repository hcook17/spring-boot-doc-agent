# ADR S-STF-A — Spec Kit WorkflowEngine vs hand-rolled runners

**Status:** Accepted · **Date:** 2026-08-08

**Decision:** Implement thin Python runners in `src/stf/runners/` with an adapter registry pattern inspired by Spec Kit’s `INTEGRATION_REGISTRY`. Do **not** depend on Spec Kit’s WorkflowEngine or `specify` CLI.

**Rationale:** This repo already has `check_repo_claims`, ast-grep mandate, and Python SoR culture. Vendoring Spec Kit’s agent command templates would fight those controls. Steal: constitution mapping (→ CONSTRAINTS.md/CLAUDE.md), phase naming, converge-as-drift concept.

**Consequences:** STF CLI owns stage machines; skills are judgment-only shells.
