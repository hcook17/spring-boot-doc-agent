---
category: spring_drift_check.py — --manifest baseline-selection research
status: research complete; design implemented same day
research date: 2026-07-25
---

# Research: which file_signatures baseline should `--manifest` prefer?

Self-contained. Grounds the design decision behind `spring_drift_check.py`'s new optional `--manifest run_manifest.json` flag (closing part of `CONSTRAINTS.md` "Integration gaps" item 3's stated residual gap: `run_manifest.json`'s `file_signatures` recording the same hash-keyed shape `spring_drift_check.py` needs for tier 1, but its CLI hardcoding a `spring_signals.json`-only interface). Read `scripts/spring_drift_check.py`'s module docstring and `scripts/run_manifest.py` directly before this research — the question below only exists because `run_manifest.json` never carries `evidence`/`entity_table_map` (so it can't replace `spring_signals.json` outright), but it does independently record `file_signatures`, sometimes at a later point in time than the scan that produced `spring_signals.json` (either copied from `--signals-file` at `init`, or freshly re-hashed at `finalize`).

## The question

When both `spring_signals.json`'s own `file_signatures` and a later `run_manifest.json`'s `file_signatures` are available as candidate tier-1 baselines, which should a drift check prefer, and on what basis — recency, or something else?

## arXiv findings

No paper found that addresses *multi-baseline selection* for a drift/staleness checker directly — consistent with `CONSTRAINTS.md` item 4's existing note that this tool's tier-1/tier-2 design already has no direct academic precedent.

- **arXiv:2606.09090**, "Context Rot in AI-Assisted Software Development: Repurposing Documentation Consistency for AI Configuration Artifacts" (Jun 8, 2026) — applies an existing README/wiki consistency checker to AI config artifacts; found staleness in 23% of 356 sampled repos. Confirms doc/code drift remains an active, unsolved problem as of mid-2026, but doesn't detail baseline-selection mechanics — abstract-level read only, not fetched further.
- **arXiv:2603.28735**, "RAD-AI: Rethinking Architecture Documentation for AI-Augmented Ecosystems" — names "cascading drift" as an ecosystem-level concern; a positioning paper, not a detection-mechanism one.
- **arXiv:2607.04281**, "Risk-Constrained Freshness-Aware Semantic Caching for Open-Web RAG" (Jul 2026) — makes the general point that naive hash comparison conflates genuine content updates with cosmetic ones (web-cache-freshness context, not code docs, but the same rationale `spring_drift_check.py`'s tier 2 already exists to address).

## GitHub prior art

- **fiberplane/drift** (https://github.com/fiberplane/drift) — a real doc-rot linter, AST-fingerprint-based (tree-sitter), multi-language (TS, Python, Rust, Go, Zig, Java), binding API/code specs to docs. Its own blog post ("We built a linter for documentation rot") documents an explicit baseline-selection hierarchy: **(1) an explicitly stamped provenance commit in the doc anchor, if present; (2) otherwise, fall back to the most recent commit that touched the spec file.** Star count and last-push recency were not independently confirmed against `00-shared-research-standards.md`'s usual star/push filter in this pass — flagged as unverified rather than presented as meeting that bar, but the design pattern itself is concrete and directly on-point regardless of the repo's popularity.
- A handful of other CI/PR-time doc-staleness checkers surfaced (jbrockSTL/doc-drift, deichrenner/driftcheck, nulone/doc-drift-guard, pallaprolus/drift-vscode) but none had surfaced documentation discussing multi-baseline selection specifically — noted as "this category of tool exists and is active" only, not as additional signal on the actual question.

## Recommendation and what was implemented

**Prefer explicit provenance over recency, not recency for its own sake.** Applied to this repo: `run_manifest.json`'s `file_signatures` aren't "more recent" in some generic sense — they're the signatures recorded by *the specific pipeline run that produced the currently-published docs*, and its `target_repo.commit_hash` is the provenance record for that. `spring_signals.json`'s signatures are the raw Stage 0 scan, which may or may not be the same run that generated what's currently published (e.g. several pipeline runs against one older scan). This mirrors fiberplane/drift's own hierarchy: prefer the explicitly stamped provenance record over a bare recency heuristic.

Implemented in `scripts/spring_drift_check.py`: a new optional `--manifest run_manifest.json` CLI flag and `manifest=` parameter on `check_drift()`. When given, `run_manifest.json`'s `file_signatures` becomes the tier-1 baseline (instead of `spring_signals.json`'s own), and the report's new `file_signatures_baseline` field records which source was used plus the manifest's `run_id`/`commit_hash`/`dirty` for provenance. `spring_signals.json` remains required in all cases, since tier 2 needs its `evidence`/`entity_table_map` regardless of which file supplied the tier-1 baseline. No new dependency added; `run_manifest.json` is read with plain `json.load`, same as everywhere else in this codebase.
