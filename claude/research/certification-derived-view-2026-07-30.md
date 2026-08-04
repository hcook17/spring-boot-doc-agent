# Certification as a derived view (B2.5) — 2026-07-30

**Verdict: REFINE** (post-B2)

B2 closed vacuous verify (`certified: true` + `mock`/`none`). It did not make
`certification.json` a recomputable derived artifact. This note locks the
DDIA-aligned model implemented in the same change set.

Aligns with: DDIA 2e Ch1 (SoR vs derived), Ch5 (schema evolution), Ch6 (LWW is
lossy); [`../10-architecture-maturation-plan.md`](../10-architecture-maturation-plan.md);
[`schema-contracts-decision-memo-2026-07-30.md`](schema-contracts-decision-memo-2026-07-30.md);
[`adoption-blockers-queue-2026-07-30.md`](adoption-blockers-queue-2026-07-30.md).

---

## 1. System of record vs derived

| Layer | Artifact / fact | Who writes |
|-------|-----------------|------------|
| SoR (run) | Stage execution facts (`name`, `status`, `executor`, `detail`) | `local_runner` / live derivation |
| SoR (run) | Gate execution facts (`id`, `status`, `required`, …) | runner gates / `live_gates` |
| Derived | `certification.json` | **only** `build_certification_report` → `write_certification_json` |

Writers pass facts. They do not invent `certified`. `generative_executor` is an
input to the fold and must be **consistent** with stage `executor` values.

**Bare-minimum honesty:** every report stamps
`completeness_claim: "fold_of_recorded_rows"`. `certified: true` means the fold
over **recorded** stage/gate rows had an empty `failures` list — not Stage-0
covering, not gap_probe measurement, not doc quality. Required stages that were
never recorded emit `stage:<name>:missing` (omission ≠ success). Live rewrite
may satisfy generative required names via an ok `generative_external` row;
deterministic required names must still be present. `--signals-file` reuse
records `signal_scan` as ok (reused), not omitted.

## 2. Schema version policy

`CertificationReport.schema_version` stays at **1**.

`StageRecord.executor` (`deterministic | none | mock | live`, default
`deterministic`) is an **additive, defaulted** field — forward-compatible for
readers that ignore unknown keys, backward-compatible via the default. That is
DDIA Ch5 evolution without a cutover.

**Bump `schema_version` only for incompatible changes** (remove/rename fields,
change `certified` semantics, require new fields without defaults). Do not bump
for additive optional fields on this ephemeral per-run derived view — hollow
version theater trains the wrong habit and dilutes real bumps on artifacts that
actually cross run boundaries (`spring_signals`, `facts.jsonl`).

Readers accept older rows missing `executor` (Pydantic default). Writers emit
the constant above.

## 3. Fold rules (`build_certification_report`)

- Gate: required gate must be `ok`; missing profile gate id → failure (unchanged).
- Stage `fail` → failure.
- Stage `skipped` → failure **only if** the stage name is in the profile’s
  required stage set (`stages_for_profile` / `build_stage_specs()`).
- If `generative_executor == "live"` and any stage has `executor == "mock"` →
  `stage:<name>:mock_under_live`.
- Required stage name never recorded → `stage:<name>:missing` (omission ≠ success).
  Live rewrite may cover generative names via ok `generative_external`.
- CERTIFIED + `generative_executor` in `{none, mock}` without `allow_mock=True` →
  `generative_executor:<exec>:allow_mock_required`. Local mock wiring runs pass
  `--allow-mock` on `local_runner`; adoption verify still needs `--allow-mock` or
  `live`.

`verify_certification` **refolds** `build_certification_report` from stamped
stage/gate rows and rejects `certified` bit ≠ refold, failures list ≠ refold, or
`certified ∧ failures ≠ ∅`.

## 4. Live gates derivation (not LWW merge)

`live_gates` rewrites the cert by:

1. Keeping prior stages with `executor=deterministic` (or legacy rows whose
   names are in the deterministic stage set).
2. Dropping mock/live generative prior rows (not SoR for this path).
3. Appending `generative_external` / `ok` / `executor=live`.
4. Gate audit = this invocation only; `test_pipeline_stages` skipped optional.

## 5. Non-goals

B3 (strict citations / `--compliance-profile` on gates). Drift `tokens`
normalizer. Fact-store replacement of docs.
