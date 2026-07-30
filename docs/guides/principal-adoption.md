# Principal adoption brief: doc-engine on your Spring services

**Audience:** Principal / staff engineers responsible for “we will document our Spring Boot services with this stack.”

**Companion:** Step-by-step commands live in [`operator-pilot.md`](operator-pilot.md). Assign that guide to operators; use this brief for decisions, contracts, and rollout.

**If this brief and the live skill or CLI disagree, the skill / CLI wins.** Generative choreography SoT: [`adapters/claude/skills/document-spring-repo/SKILL.md`](../../adapters/claude/skills/document-spring-repo/SKILL.md) + `doc_engine.pipeline.stages.build_stage_specs()`.

---

## 1. Purpose

You are adopting **doc-engine**: a portable Stage 0 scan + optional Claude generative adapter that materializes a fixed **fourteen-file** documentation set with evidence tags and mechanical gates (`certification.json`).

This is **not** a generic “AI wiki.” It is a Spring-oriented pipeline with an explicit interview for facts static analysis cannot know, and explicit `[Unknown]` when neither code nor humans can confirm.

---

## 2. Product shape (one page)

| Layer | Role | Location |
|-------|------|----------|
| **Kernel** | Scan, partition, edges, pipeline runner, compliance profiles, CLI | `src/doc_engine/` (`pip install` → `doc-engine`) |
| **Product tools** | Stage 0 + gates/validators | `python -m doc_engine.tools.*` / `doc-engine pipeline …` |
| **Claude adapter** | Live generative stages + hooks + skills | `adapters/claude/` |
| **Meta** | This monorepo’s CI claims, mutate, rule coverage | `scripts/` — do **not** ship into customer trees |

Detail: [`docs/product-architecture.md`](../product-architecture.md).

| Path | Meaning for your org |
|------|----------------------|
| **A — Deterministic** | Evidence + grouping + certification for `deterministic_only` / `scan_only`. No prose. Cheap validation that a service is “in shape” for docs. |
| **B — Full pipeline** | Path A artifacts + LLM stages + human interview → `docs/*.md` + `pipeline gates`. |

Default Stage 0 scanners: **`filesystem` + `ast-grep`**. CodeQL is **opt-in** (`--scanners filesystem,codeql`). See [`CONSTRAINTS.md`](../../CONSTRAINTS.md) Runtime prerequisites.

---

## 3. When to adopt / when not

**Adopt when:**

- Services are **Spring Boot** (Data / Security patterns are the taxonomy’s sweet spot).
- You want **onboarding and change-impact docs** that stay tied to citations, not a one-shot chat dump.
- You can name **owners** for interview answers and for signing off `[Unknown]` items.

**Do not adopt (yet) when:**

- The estate is mostly non-Java / non-Spring.
- Leadership expects **unattended fleet documentation** with no service owners.
- You need multi-repo batch orchestration, RBAC, or a complete audit product — those are open enterprise gaps ([`CONSTRAINTS.md`](../../CONSTRAINTS.md)).
- You expect perfect inheritance / meta-annotation resolution from the default scanner — precision limits are documented; treat Stage 0 as strong source-text evidence, not a compiler.

---

## 4. Recommended rollout

```text
Service 1: Path A → spot-check signals
        → Path B → human review of Unknowns + config/redaction
        → calibrate capacity_preflight expectations
Service 2+: repeat; only then widen
Never: unattended “document all N services” on day one
```

1. **One** small/medium service end-to-end (operator guide).
2. Record wall-clock, interview burden, gate failures, Unknown density.
3. Run `capacity_preflight` on the **largest** service you *intend* to cover before promising dates ([`docs/adoption-hardening.md`](../adoption-hardening.md)).
4. Only then schedule a second service with a trained operator.

Packaging of *this* product repo is paused as complete enough for pilots ([`STATUS.md`](../../STATUS.md)). Next *product* engineering investment is **fact-store Phase 1** (richer grounding) — useful after pilots, not a gate for first contact.

---

## 5. Contracts to enforce on teams

| Contract | Requirement |
|----------|-------------|
| **Evidence tags** | Generated claims use Evidenced / Confirmed / Unknown discipline; Unknowns are tracked, not silently deleted. |
| **Gates before “done”** | `doc-engine pipeline gates` + `certification verify` after live Path B. No “Claude finished chatting” = done. |
| **Interview ownership** | Named humans answer or skip; skipped items become Unknown or deferred work, not invented facts. |
| **Secrets** | No committing real credentials; treat redaction as heuristic; review configuration.md. |
| **Docs location** | Fourteen files under the **target** service’s `docs/`; do not overwrite root `README.md` when one exists (`docs/readme.md`). |
| **Profile** | Optional target `.doc-engine.yml` for `compliance_profile`; teams understand mock vs live certification. |
| **Invoke surface** | `doc-engine` / `python -m doc_engine.tools.*` only — no revived `scripts/` product shims. |
| **Skills SoT** | Edit / teach from `adapters/claude/skills/`; root `skills/` is a mirror. |

---

## 6. Risk register

| Risk | Mitigation |
|------|------------|
| Scanner misses inherited annotations / indirect interfaces | Document as known precision limit; escalate contested facts to interview or Unknown. |
| Secret leakage into docs | Redaction zones + post-run `check_no_secrets_leaked`; human review of config docs. |
| Outbound research exfiltrating internal names | Agent rules + deny raw network for Bash agents; frame WebFetch queries generically. |
| Mock certification mistaken for quality | Train teams: `generative_executor: mock` = structural only. |
| Dual skill trees diverging | CI hash gate; always start at adapter SoT. |
| Cost/latency on large repos | `capacity_preflight` before Path B; size the first pilots down. |
| Stale docs after code change | Periodic `spring_drift_check` + deliberate re-run (not continuous auto-publish). |
| Meta-repo CI / branch protection | Separate from target-service adoption; see org checklist below. |

---

## 7. Org checklist (condensed)

From [`MATURITY_ASSESSMENT.md`](../../MATURITY_ASSESSMENT.md) adoption gate and [`CONSTRAINTS.md`](../../CONSTRAINTS.md) enterprise items — split by **product repo** vs **target services**.

### This product repository (meta)

- [ ] Branch protection + required CI + review on `main` (exact `gh api` in CONSTRAINTS / [`adoption-hardening.md`](../adoption-hardening.md)).
- [ ] License / author fields still match what you ship (`MIT` today).
- [ ] Depend on pinned `requirements.txt` for operator machines.

### Target services (your estate)

- [ ] At least one Path A + Path B pilot with human review of Unknowns.
- [ ] `capacity_preflight` on largest intended service; thresholds reviewed against reality.
- [ ] Semantic eval run once on a real Path B artifact dir ([`semantic-pipeline-eval` skill](../../adapters/claude/skills/semantic-pipeline-eval/SKILL.md)).
- [ ] Named owners per service for interview + doc sign-off.
- [ ] Drift / re-doc cadence agreed (e.g. major release or quarterly).

**Not a pilot blocker:** fact-store Phase 1, multi-repo batch, RBAC.

---

## 8. Implementation playbook template (copy per service)

```text
Service name:
Repo URL / local path:
Owners (interview):
Owners (doc sign-off):
First Path A date / run_dir:
First Path B date / run_dir:
Compliance profile:
.doc-engine.yml present? (y/n):
capacity_preflight summary:
Gate result (pass/fail + notes):
Unknown items accepted for v1:
Secrets/config review done? (y/n):
Next drift re-scan date:
Link to committed docs/ PR:
```

---

## 9. Pointers

| Need | Go here |
|------|---------|
| Operator steps (A then B) | [`operator-pilot.md`](operator-pilot.md) |
| Live generative SoT | [`document-spring-repo/SKILL.md`](../../adapters/claude/skills/document-spring-repo/SKILL.md) |
| Kernel vs adapter | [`product-architecture.md`](../product-architecture.md) |
| Constraints / precision / enterprise | [`CONSTRAINTS.md`](../../CONSTRAINTS.md) |
| Product next investment | [`STATUS.md`](../../STATUS.md) (fact-store Phase 1) |
| Meta hardening ops | [`adoption-hardening.md`](../adoption-hardening.md) |
| Taxonomy of the fourteen files | [`doc-taxonomy.md`](../../adapters/claude/skills/document-spring-repo/references/doc-taxonomy.md) |
