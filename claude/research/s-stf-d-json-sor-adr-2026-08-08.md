# ADR S-STF-D — JSON/Pydantic SoR + markdown projection

**Status:** Accepted · **Date:** 2026-08-08

**Decision:** System of record is `SPEC.json` / `TASKS.json` (Pydantic, `schema_version`). Markdown (`SPEC.md`, optional TASKS.md) is a derived projection for humans/agents.

**Rationale:** DDIA schema evolution + this repo’s claims checker need typed fields. Prompt-only markdown (ehe-STF) drifts silently.

**Consequences:** `python -m stf validate` reads JSON; skills must not bypass validators.
