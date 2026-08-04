# Gap probe measurement design (DDIA-grade)

**Date:** 2026-07-30  
**Status:** Normative for `GAP_PROBE_SCHEMA_VERSION = 1`  
**Tool:** `python -m doc_engine.tools.gap_probe`  
**DDIA:** `sor-vs-derived`, `rel-gate-needs-witness`, `rel-schema-outlives-writers`; coverage denominator discipline ([`dev-coverage-denominator-codeql`](../../docs/design/ddia-north-star/deviations/dev-coverage-denominator-codeql.md), [`coverage-gates`](../../docs/design/ddia-north-star/playbooks/coverage-gates.md))

This memo replaces anecdotal ocs triage. Gaps are **residual uncertainty** quantified as rates with **closed denominators**. Absolute counts alone are not a measurement.

---

## 1. Layers (SoR vs derived)

| Layer | Role | Gap meaning |
|-------|------|-------------|
| Path A `spring_signals.json` | SoR for cert Path A | Contested identity, missing evidence strata |
| Facts `facts.jsonl` (ledger v2) | SoR for claim-symbols | Illegal `MAPS_TO` subjects, missing qualifiers |
| Path A ↔ facts join | **Derived** | Dual-SoR tension as \(R_{\text{join}}\) |
| Query lineage on `raw_queries` | **Derived** | Soft-degrade / null extract / dialect fail — not “DB wrong” |
| Dep vs code evidence | **Derived** | Dependency present without code hits in family |

Never promote a derived failure into “entity SoR wrong” without a join proof.

---

## 2. Rates (closed denominators)

| Id | Formula | Denominator | Target / note |
|----|---------|-------------|----------------|
| `R_sym` | parseable type `MAPS_TO` / all `MAPS_TO` | \|MAPS_TO\| | 1 after L3 |
| `R_coll` | contested map keys / \|entity_table_map\| | \|entity_table_map\| | 0 ideal; latent risk |
| `R_join` | Path A entries matched to ≥1 type `MAPS_TO` via fqcn or (package, simple) / \|entity_table_map\| | \|entity_table_map\| | 1 when dual-emit healthy |
| `R_lin_s` | lineage.available / queries in stratum \(s\) | \|queries\|_s | Strata below |
| `R_code_dep` | code evidence hits in family / dep signals in family | \|dep family\| | Low ⇒ taxonomy/under-claim risk |

**Lineage strata \(s\):** `native`, `jpql`, `null_query` (query field missing), `other`.  
Unavailable rows are classified by reason prefix (`InvalidSyntaxException`, `contested`, …) into failure taxonomy counts — mixture of failure modes, not one headline percentage without strata.

**Entity recall:** only when an oracle stratum is supplied. Without oracle, report `|entity_table_map|` and stratum definition — **never invent recall**.

---

## 3. Uncertainty mass

Fixed weights (not tuned per narrative):

| Weight | Value | Term |
|--------|-------|------|
| \(w_c\) | 0.30 | \(R_{\text{coll}}\) |
| \(w_j\) | 0.25 | \(1 - R_{\text{join}}\) |
| \(w_\ell\) | 0.30 | \(1 - \bar R_{\text{lin}}\) where \(\bar R_{\text{lin}}\) is size-weighted mean of strata with denom > 0 |
| \(w_d\) | 0.15 | \(1 - R_{\text{code|dep}}\) (1 if no dep signals) |

\[
U = w_c R_{\text{coll}} + w_j (1-R_{\text{join}}) + w_\ell (1-\bar R_{\text{lin}}) + w_d (1-R_{\text{code|dep}})
\]

\(U \in [0,1]\). Use to **compare** runs/repos. Not a maturity score.

**Bare-minimum honesty (artifact stamps):** when every Path A rate dens is
undefined, publish \`U: null\` with \`claim: vacuous_no_support\` (or
\`vacuous_no_support_with_s3_stamps\` if ABSENCE/UNPROVEN counts are nonzero) —
never \`0.0\` as healthy-empty. Claim ladder when dens exist:
\`comparison_index_with_unscored_s3\` (ABSENCE/UNPROVEN present) >
\`comparison_index_partial_support\` (some dens imputed) >
\`comparison_index_full_support\`. \`callable_absence\` / \`unproven\` /
\`imputed_axes\` always ride on the uncertainty block; they are **not** folded
into \(U\).

**S3 deeper close:** \(R_{\text{absence}}\) is **failure mass**
\(|\mathrm{ABSENCE}| / |\text{callable trials}|\) (ideal 0) — not identity
\(|A|/|A|\). Hits>0 families emit no ABSENCE/UNPROVEN stamp but still count in
the callable-trial denominator. \(R_{\text{recall}}\) requires a **trusted**
CodeQL covering receipt (`claim: measured`); planted `RECALL_MISS` without that
arm stamps `untrusted_planted` and stays omitted.

---

## 4. Design reopen thresholds (predeclared)

| Tension | Reopen when |
|---------|-------------|
| Path A → symbols | \(R_{\text{coll}} > 0\) on a target corpus **or** product consumer needs join and \(R_{\text{join}} < 1\) |
| Facts on cert | Before/after probe shows \(U\) drop when gates read facts |
| Lineage investment | Dominant failure stratum (by count) on measured corpus with product bite |
| Capacity 80k | Separate Stage-4 `measured_stage4_inputs` family — **out of scope** for this probe |

L5/L6 remain schema/hygiene unless this probe’s rates show otherwise.

---

## 5. Artifact

- `gap_report.json` — rates, weights, strata, versions (`GAP_PROBE_SCHEMA_VERSION`, signals `schema_version` / `scanner_version`, facts ledger version if known), deterministic key order.
- `gap_failures.jsonl` — one object per failure: `layer`, `stratum`, `reason_class`, locator fields. Sorted.

Inputs: `--signals`, `--facts` (required). Optional `--repo` reserved for future oracle walks; v1 dep/code strata use evidence bags only.

---

## 6. Falsifiers (tests)

| Fixture intent | Expected rate move |
|----------------|-------------------|
| Contested two-package `User` in map | \(R_{\text{coll}}\) increases |
| MAPS_TO with bare `User` subject | \(R_{\text{sym}}\) decreases (probe still scores; write path rejects separately) |
| Null-query raw_queries rows | `null_query` stratum denom > 0; not mixed into native available |

---

## 7. Non-goals

L5 `drift_report` schema; inventing 80k; Path A rekey in the probe PR; LLM semantic eval as gap SoR; treating zero evidence buckets as absence without dep/code strata.

---

## 8. Related measurement literature (transfer, not branding)

These sources justify **callable vs scored** strata and **cover ≠ reconstructable** discipline. They do **not** justify Phred-like QUAL on \(U\), FDR control on reopen gates, or “paralog = contested.”

| Source | Role for this probe |
|--------|---------------------|
| [arXiv:2507.03718](https://arxiv.org/abs/2507.03718) — *Finding easy regions for short-read variant calling from pangenome data* | Primary transfer: **confident/easy (callable) regions** dominate reported error; eval without them understates risk. Maps to isolating `null_query` / uncallable lineage from native/jpql \(R_{\text{lin},s}\). |
| [arXiv:2405.05734](https://arxiv.org/abs/2405.05734) — *On the Coverage Required for Diploid Genome Assembly* | Coverage **theory**: Lander–Waterman-style touch (\(c_{\mathrm{LW}}\)) is necessary but not sufficient for reconstruction; normalized \(\bar c = c/c_{\mathrm{LW}}\). Conceptual support for closed denominators and “hit count ≠ done” — **not** a plug-in formula for Spring evidence bags. |
| HPRC2 bioRxiv [10.64898/2026.07.21.739710](https://doi.org/10.64898/2026.07.21.739710) (2026-07-22) — *A human pangenome reference with near-complete coverage of common genetic variation* | **2026** multi-sample / multi-reference story: coverage of common variation across a haplotype cohort; off-reference needs a formal coordinate system. Transfer: compare \(U\) and strata across corpora; do not treat one Path A bag as the whole universe. Preprint, not VoR. |

Operational vocabulary borrowed from the above: **callable denominator** (rows eligible for a rate) vs **success numerator** (rows that pass). Absolute failure counts remain non-measurements.

---

## 9. Measured corpus: ocs `local-runs/ocs-l3-symbol` (2026-07-30)

Command (artifacts: `local-runs/ocs-l3-symbol/gap_report/`, untracked):

```text
PYTHONPATH=src python -m doc_engine.tools.gap_probe \
  --signals local-runs/ocs-l3-symbol/spring_signals.json \
  --facts local-runs/ocs-l3-symbol/facts.jsonl \
  --out local-runs/ocs-l3-symbol/gap_report
```

| Metric | Value |
|--------|-------|
| \|entity_table_map\| / \|MAPS_TO\| / \|raw_queries\| | 53 / 53 / 198 |
| \(R_{\text{sym}}\) | 1.0 |
| \(R_{\text{coll}}\) | 0.0 |
| \(R_{\text{join}}\) | 1.0 |
| \(\bar R_{\text{lin}}\) | 0.490 (native 97/191; jpql 0/1; null_query 0/6) |
| \(R_{\text{code|dep}}\) | 0.167 (1/6 family-weighted) |
| \(U\) | 0.278 |
| Dominant lineage failure class | `dialect_or_syntax` (95) |

**Threshold application (memo §4):** Path A → symbols **does not reopen** (\(R_{\text{coll}}=0\), \(R_{\text{join}}=1\)). Lineage investment **candidate** (dominant `dialect_or_syntax`). Capacity 80k **out of scope**. L5/L6 stay next schema/hygiene work unless a later probe shows otherwise.
