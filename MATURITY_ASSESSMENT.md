# Maturity Assessment

A standing, in-place-edited scorecard for anyone evaluating `spring-boot-doc-agent` for use beyond a single operator's own machine — a different axis from `CONSTRAINTS.md` (the catalog of individual facts this scorecard's ratings are grounded in) and `STATUS.md` (done/pending tracking for the steering-prompt work driving this repo's own evolution). Read this file for "how mature is this, overall, and what has to be true before wider adoption"; read the other two for the itemized facts behind that judgment.

Written 2026-07-23, after adding `skills/semantic-pipeline-eval/` and `skills/capacity-preflight/` (see `claude/session-log.md`'s entry for this date). Every rating below cites a real file, test count, or documented gap — not an unverified impression — the same evidence discipline `doc-taxonomy.md`'s `[Evidenced]`/`[Unknown]` tagging already enforces on this plugin's own generated output.

---

## Scorecard

| Dimension | Rating | Grounded in |
|---|---|---|
| Testing depth | **Moderate-to-strong, mechanical; semantic layer newly scaffolded, not yet exercised against a real run** | Nine `unittest` suites (`test_spring_signal_scan.py`, `test_partition_repo.py`, `test_spring_drift_check.py`, `test_pipeline_stages.py`, `test_secret_heuristics.py`, `test_config_keys.py`, `test_verify_llms_docs.py`, plus this change's `test_semantic_eval_helpers.py` and `test_capacity_preflight.py`), all passing locally, all wired into `.github/workflows/ci.yml`. `test_pipeline_stages.py` is explicitly mechanical (tag grammar, citation resolvability, JSON shape) — it does not judge truthfulness. `skills/semantic-pipeline-eval/` now provides that judgment layer, but it's an LLM-driven skill by nature, not a headless CI check — it has never been run against a real completed pipeline output as of this writing. |
| Scalability / load-tested-ness | **Measurable per-repo now; still unvalidated at real scale** | `skills/capacity-preflight/` turns `CONSTRAINTS.md`'s prose scale-assumptions (chars/N token heuristic, uncapped fan-out, repo-wide `references` bucket sent to every Stage-1 dispatch) into concrete numbers via `scripts/capacity_preflight.py`, which imports (does not re-derive) `partition_repo.py`'s/`spring_signal_scan.py`'s own logic. It has been run against the small `scripts/test_fixtures/spring_signals/` fixture only (1 group, 18 dispatches, ~783 est. tokens) — never against an actual large/monorepo target, so the warning thresholds themselves (15 groups, 40 dispatches, 500,000 references-bucket tokens) are stated as tunable guesses, not calibrated values. |
| Schema & contract rigor between stages | **Weak — unchanged by this work** | The four inter-stage JSON artifacts (`spring_signals.json`, `groups.json`, `summaries.json`, `interview_answers.json`) still have no schema or validation, per `claude/steering-prompts/02-pluggability-research-prompt.md`'s still-open finding — `summaries.json` already drifted once (gained `cross_group_relationships` after the prompt describing it was written) with nothing catching the shape change. Both new scripts added by this change (`semantic_eval_helpers.py`, `capacity_preflight.py`) are two more consumers of these unschema'd contracts, raising the cost of ever changing their shape without a schema — this closes no part of the gap itself. |
| Observability / telemetry | **Weak — pre-run estimate exists, no post-run record** | No `run_manifest.json` exists (`CONSTRAINTS.md` "Integration gaps" item 3, `claude/steering-prompts/04-analytics-logging-research-prompt.md` item 2, both still open). `capacity-preflight` produces a *pre-run* estimate only; nothing today records what a run's *actual* fan-out, token spend, or evidence-tag breakdown turned out to be, so the preflight's own predictions can't be checked against reality yet. |
| Security & governance | **Weak** | No RBAC or auth layer of any kind (`CONSTRAINTS.md` "Enterprise-readiness gaps" item 2 — confirmed by absence). No audit trail of pipeline runs (item 3). Secret/credential redaction exists and is tested (`scripts/_secret_heuristics.py`, `test_secret_heuristics.py` 13/13) but is explicitly heuristic, not exhaustive. **Stale-documentation finding from this audit**: `CONSTRAINTS.md`'s "Enterprise-readiness gaps" item 1 and `STATUS.md`'s "Pending" section both still say the license is `"UNLICENSED"` — `.claude-plugin/plugin.json`'s `license` field actually reads `"MIT"` as of this audit. This is exactly the kind of doc/reality drift `claude/steering-prompts/03`'s confidentiality rule and this project's own drift-detection tooling exist to catch elsewhere; corrected in `CONSTRAINTS.md` as part of this change (see cross-reference edits). |
| Dependency reproducibility | **Weak — unchanged** | No `requirements.txt`/`pyproject.toml` exists; `ast-grep`, `sqllineage`, `pathspec` are all unpinned (`CONSTRAINTS.md` "Runtime prerequisites" item 4). Neither new script adds a third-party dependency (both are stdlib-only, confirmed by their own imports), so this change doesn't worsen the gap, but doesn't close it either. |
| Documentation & handoff quality | **Strong** | `CONSTRAINTS.md`, `STATUS.md`, `CONTRIBUTING.md`, `claude/session-log.md`, and `skills/document-spring-repo/references/doc-taxonomy.md` collectively give a new contributor (or a cold session) a single, cross-linked place to learn this repo's real state rather than reconstructing it from commit history — the same design principle this file follows. |

## Drift from modern practice

- **Prose-only inter-stage contracts vs. schema-validated contracts.** Modern multi-agent/multi-stage LLM pipelines increasingly validate inter-stage JSON with an explicit schema (JSON Schema, Pydantic models, or similar) so a shape change fails loudly at the producing stage rather than silently at an unrelated consumer months later. This repo's four inter-stage artifacts have none — see the scorecard row above.
- **Mechanical-only testing vs. semantic-eval harnesses for LLM pipelines.** `test_pipeline_stages.py`'s own commit (per `claude/session-log.md`) cites real precedent for this gap: arXiv:2604.25359 shows schema compliance and value accuracy diverge sharply in structured LLM output, and `promptfoo` (23.5k+ GitHub stars, confirmed via `gh api`) is a current, maintained example of the eval-harness-over-LLM-judge pattern this project already leans toward. `skills/semantic-pipeline-eval/` is a first step toward closing this specific drift — genuinely new capability, not previously present in any form — but it is a manually-invoked skill, not a CI-integrated harness; a promptfoo-style automated eval gate on every prompt change remains open.
- **CI without branch-protection enforcement vs. required-status-checks as baseline practice.** `.github/workflows/ci.yml` runs a real, passing test suite on every PR, but `CONSTRAINTS.md` item 6 confirms directly (via a live GitHub PR audit) that nothing requires it to pass before merge — `Checks: 0`, no required reviews. Baseline modern practice treats "CI exists" and "CI is enforced" as two separate, both-required steps; this repo has only the first.
- **Unpinned dependencies vs. lockfiles as baseline practice.** No `requirements.txt`/`pyproject.toml`/lockfile of any kind — a modern minimum-bar expectation for anything beyond a single-operator script.

## Named limitations and paths forward

**What the two new skills concretely close:**
- A previously-nonexistent semantic/hallucination-detection layer for the four LLM pipeline stages (`skills/semantic-pipeline-eval/`), directly extending the scope `claude/steering-prompts/01-testability-research-prompt.md` originally named and only partially closed (mechanical checks only).
- A previously-nonexistent, per-repo, measurable answer to "will this run be too big" (`skills/capacity-preflight/`), replacing prose assumptions in `CONSTRAINTS.md`/`SKILL.md` with actual numbers for a specific target repo.

**What remains fully open — not touched by either new skill:**
- Schema/contract validation between pipeline stages (`claude/steering-prompts/02`).
- Post-run telemetry / `run_manifest.json` (`claude/steering-prompts/04` item 2) — note the natural follow-on this audit surfaces: a future manifest should record `capacity-preflight`'s *predicted* numbers next to the run's *actual* observed fan-out/tokens, closing a calibration loop that doesn't exist yet.
- RBAC, multi-repo/batch support, audit trail, dependency pinning, and branch-protection enforcement — all still exactly as open as `CONSTRAINTS.md`'s "Enterprise-readiness gaps" section already states, in the same close-out order that file recommends.
- CI-automated semantic evaluation — `semantic-pipeline-eval` is manually invoked today; it cannot run headless in `.github/workflows/ci.yml` the way the mechanical suites do, since it requires a live LLM-driven session.

## Adoption gate checklist

Minimum concrete items before this pipeline is adopted beyond a single operator's own machine, ordered to match `CONSTRAINTS.md`'s existing close-out sequence:

- [ ] License resolved and consistently documented — `.claude-plugin/plugin.json` already says `MIT`; `CONSTRAINTS.md`/`STATUS.md` corrected to match as of this change, but re-confirm before relying on either doc.
- [ ] Branch protection enabled on `main` requiring the existing CI workflow to pass and at least one review, per the exact `gh api` command already given in `CONSTRAINTS.md` item 6.
- [ ] Dependencies pinned (`requirements.txt` or `pyproject.toml` for `ast-grep-cli`, `sqllineage`, `pathspec`).
- [ ] `skills/semantic-pipeline-eval/` run at least once against a real completed pipeline run (not just synthetic fixtures), and its findings reviewed by a human.
- [ ] `skills/capacity-preflight/` run against the largest repo the organization actually intends to point this at, and its warning thresholds reviewed/recalibrated against that real result rather than left at their stated-guess defaults.
- [ ] Run-level audit trail / `run_manifest.json` built (`claude/steering-prompts/04`).
- [ ] RBAC / multi-repo support addressed, if the intended usage is multi-team rather than single-operator (lowest urgency of this list per `CONSTRAINTS.md`'s own ordering).

## Cross-links

- `CONSTRAINTS.md` — the plugin's standing constraints; this file's ratings are grounded in its entries.
- `STATUS.md` — current-state done/pending tracking for the steering-prompt work.
- `claude/session-log.md` — append-only history; see the entry for this file's own addition.
- `skills/semantic-pipeline-eval/SKILL.md`
- `skills/capacity-preflight/SKILL.md`
