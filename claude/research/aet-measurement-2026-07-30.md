# AET measurement (Association–Environment–Truncation)

**Date:** 2026-07-30  
**Status:** Normative for `GAP_PROBE_SCHEMA_VERSION = 2`  
**Companion:** [`gap-probe-measurement-design-2026-07-30.md`](gap-probe-measurement-design-2026-07-30.md) (v1 rates / reopen policy)  
**Tool:** `python -m doc_engine.tools.gap_probe`

Resolves genomics / physical-chemistry / quantum-inspired / SE / physics / math critiques into one falsifiable measurement object that **bites** in `gap_probe` — without ontology theater and without delaying L5/L6.

---

## 1. The object

Fix scanner \(S\), corpus artifacts \(C\) (signals + facts), scoring environment \(E\), truncation budget \(B \in \mathbb{N}\cup\{\infty\}\).

For each association family \(k\), a finite **callable trial set** \(\mathcal{A}_k(C,E)\) and success predicate \(\mathrm{ok}_k\):

\[
\hat r_k(C,S,E)=\frac{\lvert\{a\in\mathcal{A}_k(C,E):\mathrm{ok}_k(a)\}\rvert}{\lvert\mathcal{A}_k(C,E)\rvert}
\quad(\text{undefined if denom }=0).
\]

**Residual vector:**

\[
\hat{\boldsymbol{\rho}}=
\big(
\hat r_{\mathrm{coll}},\;
1-\hat r_{\mathrm{join}},\;
1-\bar{\hat r}_{\mathrm{lin}},\;
1-\hat r_{\mathrm{code\_dep}}
\big)\in[0,1]^4.
\]

**Comparison index** (policy weights \(w\), fixed — not a free energy):

\[
U_w(\hat{\boldsymbol{\rho}})=w\cdot\hat{\boldsymbol{\rho}}.
\]

**Scoring-environment intervention** (same bytes, two estimators):

| \(E\) | Lineage callable rule |
|-------|----------------------|
| `callable` (normative) | `null_query` trials excluded from \(\bar{\hat r}_{\mathrm{lin}}\) |
| `pooled` (contrast) | `null_query` folded into `native` as failed trials |

\[
\Delta\hat{\mathbf{r}}=\hat{\mathbf{r}}(E_{\mathrm{callable}})-\hat{\mathbf{r}}(E_{\mathrm{pooled}}).
\]

**Truncation:** \(\Pi_B\) keeps the first \(B\) failures under the deterministic sort key. With planted must-keep locator set \(M^\star\):

\[
L(B)=\frac{\lvert M^\star\setminus\mathrm{locators}(\Pi_B(\mathrm{failures}))\rvert}{\lvert M^\star\rvert}.
\]

**Measurement:**

\[
\hat{\mathcal{M}}(C,S,E,B)=\big(\hat{\mathbf{r}},\,\hat{\boldsymbol{\rho}},\,U_w,\,\Delta\hat{\mathbf{r}},\,L(B)\big).
\]

Co-occurrence across fixture ensembles and Spearman (\(n\ge 5\)) are documented protocols for multi-corpus work; schema v2 always emits single-corpus \(\hat{\mathcal{M}}\).

---

## 2. Typed slots (dimension hygiene)

| Slot | JSON path | Meaning |
|------|-----------|---------|
| Rates | `rates.*` | Empirical frequencies \(\hat r\) |
| Residuals | `measurement.residuals` | \(\hat{\boldsymbol{\rho}}\) |
| Comparison index | `uncertainty` / `measurement.comparison_index` | \(U_w\) — policy |
| Env delta | `measurement.delta_r_scoring_env` | \(\Delta\hat{\mathbf{r}}\) |
| Truncation loss | `measurement.truncation` | \(L(B)\) — not added into \(U_w\) |

Never sum across slots as if commensurate.

---

## 3. Bite axioms (tests)

| Id | Claim |
|----|-------|
| A1 | Callable vs pooled scoring moves \(\bar{\hat r}_{\mathrm{lin}}\) when `null_query` rows exist |
| A2 | Scoring-env change does not invent identity failure (\(\hat r_{\mathrm{sym}},\hat r_{\mathrm{join}},\hat r_{\mathrm{coll}}\) invariant) |
| A3 | Collision-only fixture does not force lineage-dominant reopen to dialect |
| A4 | \(B'<B \Rightarrow L(B')\ge L(B)\) on planted \(M^\star\) |
| A5 | Truncation loss lives only under `measurement.truncation` |

**Reopen** (consume \(\hat{\mathcal{M}}\); same policy as gap-probe memo §4):

- Path A → symbols: \(\hat r_{\mathrm{coll}}>0\) or (consumer-needed ∧ \(\hat r_{\mathrm{join}}<1\))
- Lineage investment: dominant failure class on callable taxonomy
- Truncation alarm: \(L(B)>\tau_L\) at declared \(B\) ⇒ do not claim failures fully reported (\(\tau_L=0\) for must-keep)

---

## 4. Expert-resolution table

| Expert demand | Where resolved |
|---------------|----------------|
| Closed denominators / callable | \(\mathcal{A}_k\); `callable_denominator` on rate objects |
| No QUAL/FDR/paralog / ΔG/bond / entanglement | Forbidden normative vocab; lit appendix only |
| \(R(C,S,E)\); intervention | Hats + scoring_env + \(\Delta\hat{\mathbf{r}}\) |
| Estimator not parameter; no CI | No confidence intervals in v2 |
| \(U\) is policy score | Typed `comparison_index` |
| Projection + loss + monotonicity | \(\Pi_B\), \(L(B)\), axiom A4 |
| Efficiency without TN theater | Carry budget on failures; MPO/χ deferred |

---

## 5. Forbidden normative vocabulary

bond, molecule, \(\Delta G\), solvent, decoherence, entanglement, bond dimension \(\chi\), Phred/QUAL-as-\(U\), FDR-as-reopen, paralog=contested, thermodynamic space↔capacity.

---

## 6. Literature appendix (transfer limits)

| Source | Transfer | Not transferred |
|--------|----------|-----------------|
| [arXiv:2507.03718](https://arxiv.org/abs/2507.03718) | Callable vs scored | Variant QUAL |
| [arXiv:2405.05734](https://arxiv.org/abs/2405.05734) | Cover ≠ reconstructable (conceptual) | Assembly coverage formulas |
| HPRC2 [10.64898/2026.07.21.739710](https://doi.org/10.64898/2026.07.21.739710) | Multi-corpus comparison intuition | Pangenome graphs as SoR |
| [arXiv:2604.14287](https://arxiv.org/abs/2604.14287) / CompactifAI [arXiv:2401.14109](https://arxiv.org/abs/2401.14109) | Truncate non-essential carry | MPO on LLM weights in this repo |

Removing this appendix must not change axioms A1–A5 or reopen predicates.

---

## 7. Non-goals

L5 `drift_report` implementation; dialect pack regen as env knob (same \(\Delta\hat{\mathbf{r}}\) shape later); MI estimators; inventing 80k; Path A rekey.
