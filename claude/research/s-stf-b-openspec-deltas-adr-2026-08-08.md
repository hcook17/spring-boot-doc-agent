# ADR S-STF-B — OpenSpec deltas for review remediation

**Status:** Accepted · **Date:** 2026-08-08

**Decision:** For `input_kind=review_remediation`, write OpenSpec-style change packs under `specs/(target)/change/` (`delta.md` + `delta.json` with ADDED/MODIFIED/REMOVED). Greenfield `feature` targets may use full SPEC overwrite without a change pack.

**Rationale:** PR #94-style work is brownfield claim correction, not greenfield product specs. Delta packs make “what we overturn” machine-readable.

**Consequences:** `stf ingest-review --spec-dir` always emits a change pack for remediation targets.
