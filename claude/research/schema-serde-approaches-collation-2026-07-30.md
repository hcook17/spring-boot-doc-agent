# Schema serde approaches collation (2026-07-30)

**Status:** research collation.  
**Inputs:** [schema-coverage-corpus-2026-07-30.md](schema-coverage-corpus-2026-07-30.md); DDIA Ch1/Ch5; Pydantic v2; in-repo Phase 1 fact-store memos; [`../deterministic-boundary-schemas-spi-research-2026-07-29.md`](../deterministic-boundary-schemas-spi-research-2026-07-29.md).

---

## 1. Problem statement

Inter-stage artifacts are **typed languages** with uneven alphabets. Four have Pydantic + exported JSON Schema; several high-risk views rely on imperative validators or nothing at the gate. Encoding is mixed (JSON object, JSON array, JSONL). Openness is mixed (`extra=allow` bags vs intended `extra=forbid` ledger). Without an explicit open/closed and write/read/cert policy, adding schemas ad hoc creates incompatible contracts (e.g. silently allowed extras on SoR).

---

## 2. Dimensions of comparison

| Dimension | Options | What it buys | What it costs |
|-----------|---------|--------------|---------------|
| **World** | Open (`extra=allow`) vs closed (`extra=forbid`) | Forward-compat vs fail-closed detection | Open hides typos; closed breaks additive emitters |
| **Validation moment** | Write-time / read-time / cert-time | Fail early vs fail at product boundary | Write-time needs producer discipline; cert-only allows bad mid-pipeline caches |
| **Encoding** | Single JSON value vs JSONL | Streaming / append-friendly ledger | Tooling must not `json.load` JSONL |
| **Versioning** | Absent / integer `schema_version` / export `x-*` | Reader lattice \(v' \ge v_{\min}\) | Missing version = implicit v0 (must document) |
| **Authority** | Model-as-SoT + derived JSON Schema vs hand schema vs imperative-only | One place to edit | Hand schemas drift; imperative duplicates Pydantic |
| **SoR vs view** | Strict ledger vs soft LLM shape | Correct investment | Over-scheming views without gate bite = theater |

---

## 3. Approaches (collated)

### A. Status quo (uneven)

- **Keep** Path A: `spring_signals` open bag + CI fixture gate; Stage 5 imperative for summaries/gaps.
- **Problem:** review findings unwired; facts emitted without closed decode; edges/cert/drift/capacity unschematized.
- **Fits:** shipping velocity already spent on dual-emit.

### B. Big-bang Pydantic everywhere

- Model all ~10–12 artifacts + export schemas + harness in one PR.
- **Reject for sequencing:** blocks B1–B4; high conflict surface; mixes operator reports with Path A cert.
- Matches anti-pattern called out in Phase 1 memo (no full JPA dump).

### C. Closed SoR first, views gated with bite (REFINE candidate)

1. Close **facts** ledger (`forbid`, JSONL validate, export schema, CI via deterministic Stage 0 `--all`).
2. Export schema for existing **CertificationReport**.
3. Promote **edges** + **gap_questions** to models (gap already has imperative — unify).
4. **architecture_testing_review** model **only with B4** wire into `run_stage5_gate`.
5. Drift/capacity last.

- **Fits:** DDIA SoR vs views; adoption-blockers queue; 2026-07-29 write-vs-read questions answered per class.

### D. Cert-time only for soft views

- Generative artifacts validated only under `certified` profile; deterministic_only skips.
- **Partial truth today:** Stage 5 runs when artifacts present; scan_only does not require LLM files.
- **Keep as policy:** do not require review/gaps for `deterministic_only`; do require them when present under certified / live gates (B2/B3).

### E. SPI / plugin schemas

- Invent entry-point SPI for artifact types.
- **Reject:** 2026-07-29 note — keep `build_stage_specs()` as registry; no third-party scanner story yet.

---

## 4. Open vs closed — recommended assignment

| Artifact | Recommended world | Rationale |
|----------|-------------------|-----------|
| spring_signals | **Open** (remain `allow`) | Evolving evidence bags; forward-compat for scanners; Path A already versioned |
| facts.jsonl | **Closed** (`forbid`) | Explicit eight-field ledger; typos must fail |
| groups | **Mostly closed** | Stable partition shape; allow dict in `skipped` only if needed |
| summaries / interview | **Closed required keys** | Already mostly closed |
| gap_questions / review | **Closed required keys** + optional documented extras (`external_research`) | Soft content, hard shape |
| cross_group_edges | **Closed top-level** + documented nested maps | Version already 1 |
| certification | **Closed** (match model fields) | Audit artifact |
| run_manifest | Keep hand schema track or later unify | Telemetry; low Path A urgency |
| drift / capacity | Open or thin closed later | Operator; not Path A |

---

## 5. Write-time vs read-time vs cert-time

| Class | Write-time | Read-time | Cert-time |
|-------|------------|-----------|-----------|
| SoR (signals, facts) | Prefer validate-on-write for facts once model lands; signals remain merge-then-gate | Consumers may trust CI + gate | `validate_artifacts` / scan_only / deterministic_only |
| Derived deterministic | Optional assert after build | Load as dict until modeled | Include in `--all` when registered |
| LLM views | Producer agent contract (prompt) | Stage 5 / Pydantic | Required under certified when files exist |
| certification | Always `CertificationReport` construct | verify CLI | Self-describing |

**Principle:** a schema without a **bite** (gate or write assert) is documentation debt. Hence review schema ↔ B4 same change.

---

## 6. Version lattice

- Readers: accept \(v' \ge v_{\min}\) where documented (`spring_signals` ≥2).
- Writers: emit current constant.
- JSONL facts: ledger version as export annotation (`x-doc-engine-schema-version`) and/or optional header line **or** keep version off-wire and document constant in module (Phase 1 chose off-wire constant — preserve unless breaking).
- Missing version on edges is OK today (always 1); do not remove field when modeling.

---

## 7. Serde testing mathematics (harness design)

Registry-driven table (artifact × property):

| Property | Predicate |
|----------|-----------|
| RT | \(\mathrm{decode}(\mathrm{encode}(x)) = \pi(x)\) |
| REQ | \(\forall k \in Required: decode(x\setminus\{k\})\) fails |
| UNK | unknown key → allow iff open else fail |
| TYPE | wrong type fails |
| LINE | `line < 1` fails when field present |
| JSONL | blank skip; bad line fails with lineno |
| CONTEST | multi-MAPS_TO arity preserved |

Unschematized artifacts: rows marked `skip`/`xfail` with reason until registered in `ARTIFACT_MODELS`.

Implement harness in first **implementation** PR (facts), not as empty research theater — one row for facts + existing four.

---

## 8. Packaging / enterprise / precision (sequencing only)

From external review §7 siblings — **not** solved by schema PRs:

| Topic | Disposition |
|-------|-------------|
| Detection precision (inheritance, Groovy, JPQL, `_first_line_match`) | CONSTRAINTS / Stage 0; separate |
| No RBAC / branch protection / multi-repo | Repo admin / product later |
| pyproject vs requirements; shims; Python 3.10 claim vs CI 3.11 | Hygiene PR after schema slices if ranked |
| semantic-pipeline-eval never on real output | B2/live cert adjacent |

---

## 9. Comparison verdict

| Approach | Verdict |
|----------|---------|
| A Status quo | Insufficient — B4 + facts gap remain |
| B Big-bang | Reject |
| C Closed SoR first + views with bite | **Accept (REFINE)** |
| D Cert-time soft views | Accept as **policy overlay** on C |
| E SPI | Reject |

→ Decision memo.
