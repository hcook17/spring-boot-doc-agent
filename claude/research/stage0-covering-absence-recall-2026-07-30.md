# Stage-0 covering proof, callable absence, and recall writers

Written 2026-07-30. Normative product design for hard stops that prior
Stage-0 work left as “undecidable forever”: (1) empty evidence bucket vs miss,
(2) entity/annotation recall without an independent writer.

DDIA anchors: `docs/design/ddia-north-star/` SoR vs derived, gate-needs-witness,
`dev-fp-ratchet-separate-from-recall`. Genomics transfer is limited to
**callable trials** (score only where an independent witness makes the claim
valid) — see also `claude/research/gap-probe-measurement-design-2026-07-30.md` §8.
Forbidden normative vocab from AET still applies (bond, ΔG, entanglement, …).

## Adversarial prior art (why naive methodology fails)

| Source | Bite |
|--------|------|
| [arXiv:2507.03718](https://arxiv.org/abs/2507.03718) | Accuracy outside callable/easy regions is invalid (~10×). **ABSENCE only inside callable trials.** |
| [arXiv:2502.14463](https://arxiv.org/abs/2502.14463) MeCheck | Spring metadata↔code; GitHub EA heuristics; FN from library RegEx — precision/recall tradeoff is explicit. Empty-bucket-as-absent is worse. |
| [arXiv:2402.14366](https://arxiv.org/abs/2402.14366) AIF | Annotations induce analyzer FNs → source-only entity recall needs a second arm. |
| [arXiv:2604.07755](https://arxiv.org/abs/2604.07755) | Static analysis has a hard upper bound &lt;100%. Refuse “full extraction” marketing. |
| [arXiv:2508.04448](https://arxiv.org/abs/2508.04448), [arXiv:2605.11163](https://arxiv.org/abs/2605.11163) | Ungrounded LLM recall is not a SoR; hybrid with deterministic writers only. |
| DeepWiki Hibernate metamodel / Spring `PersistenceManagedTypesScanner` / sql-update-check | Independent entity inventories and bidirectional missing-entity checks. |

## Four claims, four witnesses

| Claim | Witness |
|-------|---------|
| **S1 Processing covering** | `covering_proof.json`: `inventory_root = H(file_signatures)`; per-backend `acked_subset_root == expected_subset_root` |
| **S2 Projection integrity** | Existing `gap_probe` rates over Path A + facts |
| **S3 Absence** | `ABSENCE` / `UNPROVEN` facts: callable ⇔ S1 ∧ rule_pack applied ∧ **family_witness** (build dep / config keys) |
| **S3 Recall** | `RECALL_MISS` facts when an oracle arm (CodeQL and/or multipass/metamodel) writes an entity set; verdict `STRUCTURAL` \| `EVIDENTIARY` |

Spectators over positive hits alone never decide S3.

## Callable trial

```text
callable(F) ⇔
  covering_proof verifies
  ∧ ast-grep (or relevant) receipt complete for F's scope
  ∧ family_witness(F) present
```

- callable ∧ zero positive hits → `ABSENCE`
- not callable → `UNPROVEN` (never silent “feature absent”)
- soft-fail empty scan → S1 failed; no green Path A

## Artifacts

- `spring_signals.json` — Path A evidence SoR (unchanged role)
- `covering_proof.json` — sibling S1 SoR
- `facts.jsonl` — dual-emit including `ABSENCE` / `UNPROVEN` / `RECALL_MISS`
- `gap_report.json` — derived MV; must verify covering before rates; score absence/recall only from stamps

## Explicit refusals

GapObserver theater; `inventory.java_files` dump as SoR; LLM as recall SoR;
100% semantic extraction claims; Ubuntu CI as CreateProcess witness.
