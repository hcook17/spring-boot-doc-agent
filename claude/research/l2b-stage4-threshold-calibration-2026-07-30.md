# L2b Stage-4 threshold calibration research (2026-07-30)

**Status:** Closed for *default selection* — **retain `--stage4-shared-tokens-warn-threshold` default `80000`**.  
**Amendment (2026-07-30):** Review B replaced — **summer 2026** Kimi K3 tech report ([2607.24653](https://arxiv.org/abs/2607.24653)) instead of Aug 2025 RCR-Router; retain decision unchanged.  
**Not closed:** Stage-4 capacity risk (returns still omitted); mid-size `measured_stage4_inputs` run still required before *changing* the default.  
**Method:** [00-shared-research-standards.md](../steering-prompts/00-shared-research-standards.md) + [11-context-traversal-protocol.md](../steering-prompts/11-context-traversal-protocol.md) (BFS discover → DFS ground).  
**DDIA:** `rel-partition-bounds-fanout`, `claims-and-status-drift`.  
**SoR for our metric:** on-disk Stage-4 inputs via `capacity_preflight.measure_stage4_shared_pool_tokens` / CLI `--summaries-file` (PR #74). Numeric `*_upper_bound_*` fields remain warn-threshold names only.  
**Season bar for the two required arXiv reviews:** spring/summer 2026 — Review A = Apr 2026 ContextBudget; Review B = Jul 2026 Kimi K3.

---

## 0. Decision (read this first)

| Question | Answer |
|----------|--------|
| Change default from 80000? | **No — retain.** |
| Why not raise/lower from papers? | No Tier-A source maps a transferable number onto *our* chars/N shared-pool × `VALID_DOC_FILES` fan-out. Budgets in prior art are context-window B, per-agent memory B, or **dollar/iteration** caps — different SoR. |
| When may the default change? | After a **documented mid-size run** exercising `measured_stage4_inputs` (summaries + interview + signals) with measured shared-pool vs Stage-0 proxy, written into an update of this note. |
| Invent interview sizes at Stage 0? | **Still forbidden.** |

---

## 1. Two independent arXiv reviews

Distinct mechanisms (not two write-ups of one paper). Abs pages opened and claims re-read in HTML.

### Review A — ContextBudget / BACM (arXiv:2604.01664)

| Field | Value |
|-------|--------|
| Abs | https://arxiv.org/abs/2604.01664 |
| Mechanism | **Budget-Aware Context Management:** treat context compression as a sequential decision under an **explicit context-window budget** B; expose remaining headroom *before* loading the next observation; train BACM-RL with a **progressively tightened budget curriculum** and overflow penalties. |
| Tier | **A** (primary: abs + HTML paper body §1–3) |
| Maps to L2b? | **Partially.** Confirms that budgets must be **explicit and measured against remaining capacity**, and that budget-free heuristics fail (over-compress under loose B / under-compress under tight B). |
| Does **not** map | Curriculum stages (e.g. 8k→4k in companion materials) are **agent context-window** budgets for search agents — not our Stage-4 shared JSON pool warn threshold. |

**CONFIRMED claims (A):**

1. Context growth vs fixed B is a real deployment constraint — paper §1 (abs/HTML).  
2. Budget-free compression is a failure mode (over/under-compress) — paper §1.  
3. Useful control exposes remaining budget before appending new payload — paper §3.1 (`r_t = B - |C_t|`).

**REFUTED for our default:**

- “Therefore set Stage-4 warn default to X tokens.” — **no such transfer function** in the paper.

**Companion GitHub:** `yw-0311/ContextBudget` — **2 stars**, pushed 2026-04-07 — fails 00 star/adoption bar as a *comparator*; treated as paper artifact only, not a serious GitHub candidate.

### Review B — Kimi K3 tech report (arXiv:2607.24653) — summer 2026

| Field | Value |
|-------|--------|
| Abs | https://arxiv.org/abs/2607.24653 |
| Season | **July 2026 (summer)** — preferred over Aug 2025 RCR-Router for the second independent review |
| Mechanism | **Open frontier MoE agent model** (2.8T / ~104B activated): Kimi Delta Attention + Attention Residuals for long-sequence information flow; **1M-token context**; post-training RL across general / **agentic** / coding; infra for million-token agentic RL. Positions long-horizon coding and agent execution as first-class; overall still trails strongest proprietary peers (Fable 5 / GPT-5.6 Sol class) on some suites. |
| Tier | **A** (primary: abs page opened 2026-07-30; full body claims to be re-checked against PDF/HTML when expanding DFS) |
| Maps to L2b? | **Partially.** Confirms that **long-horizon agent workloads** and **large context windows** are the deployment reality our Stage-4 shared pool sits in — measure load; do not assume “quiet Stage-1 ⇒ Stage-4 fine.” Supports **routing** high-volume stages toward cost-efficient long-context models without inventing a warn default. |
| Does **not** map | 1M context is a **model ceiling**, not a transferable Stage-4 chars/N warn threshold for `measured_stage4_inputs` × `VALID_DOC_FILES`. |

**CONFIRMED claims (B):**

1. Long-horizon agentic/coding execution is a first-class training/eval target at frontier scale — abs.  
2. Architecture invests in **long-sequence** attention efficiency (KDA / AttnRes) — abs.  
3. Overall performance still trails the strongest proprietary models on the authors’ suite — abs (honesty: peers, not free lunch).

**REFUTED for our default:**

- “1M context ⇒ raise `--stage4-shared-tokens-warn-threshold` to N.” — **wrong SoR** (model window ≠ our measured shared-pool warn).

**Universal apply-where-it-applies (product):** route high-volume Stage-1/4 drafts to K3-class long-context economics when model choice exists; keep **measured** preflight; retain premium models for judgment-heavy stages. Does **not** close return-payload omission.

**Demoted (older):** RCR-Router arXiv:2508.04903 (Aug **2025**) — kept only as related-work on per-agent memory B saturation; no longer one of the two required independent reviews.

### BFS-discovered tertiary (not one of the two required reviews)

**Agent Capsules** (arXiv:2605.00410, May 2026 spring) — multi-agent pipeline compound vs fine execution; **controlled negative result** that injecting *more* context into a merged call can **worsen** compression/quality; compares to LangGraph 14-agent pipeline on tokens. Used as BFS ring fuel → DFS seed for “merged shared pool ≠ free lunch.”

**Also summer 2026 (frontier, not Review B):** TokenPilot [2606.17016](https://arxiv.org/abs/2606.17016), CWL structured eviction [2606.11213](https://arxiv.org/abs/2606.11213) — context-under-budget mechanisms; still no transferable 80k.

---

## 2. GitHub comparators (00 bar)

| Repo | Stars (2026-07-30) | `pushed_at` | Adoption signal | DeepWiki | Role |
|------|-------------------:|-------------|-----------------|----------|------|
| [BerriAI/litellm](https://github.com/BerriAI/litellm) | **55116** | 2026-07-30 | Gateway/SDK widely deployed; docs + PyPI; continuous pushes | Indexed (2026-07-29) — **Tier C only** | Primary: **budget enforcement** as product feature |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | **38518** | 2026-07-30 | Default multi-agent orchestration stack; cited by Agent Capsules | Indexed (2026-07-02) — **Tier C only** | Secondary: **fan-out / shared state** mental model |
| [MoonshotAI/Kimi-K3](https://github.com/MoonshotAI/Kimi-K3) | **7519** | 2026-07-28 | Flagship open-weight release companion to arXiv:2607.24653; recent push | Check deepwiki.com/MoonshotAI/Kimi-K3 (Tier C if indexed) | Tertiary: **long-context / agent model** SoR for Review B |
| yw-0311/ContextBudget | 2 | 2026-04-07 | Paper code only | n/a | **Rejected** as GitHub comparator (stars) |

### DeepWiki orientation (Tier C → leave)

- **litellm:** orients dual SDK/proxy modes; spend tracking / hierarchical budgets as first-class. **Did not** treat wiki prose as CONFIRMED.  
- **langgraph:** orients StateGraph / checkpoint / BSP execution. Useful for “multi-actor shared state” vocabulary — not for our 80k number.

### DFS to Tier A (re-verify)

**Path — “Budgets are enforced against measured session usage, not static poetry”**

1. DeepWiki litellm (Tier C) → points at budget/spend concepts.  
2. Primary docs: [Agent Iteration Budgets](https://docs.litellm.ai/docs/a2a_iteration_budgets) (Tier A for product behavior).  
3. **CONFIRMED:** LiteLLM caps **max_iterations** and **max_budget_per_session ($)** using session/trace ids; exceeds → 429. Budgets are **operational counters**, not guessed shared-pool chars/N defaults for a doc pipeline.

**Path — “Orchestration frameworks share state across actors”**

1. DeepWiki langgraph (Tier C).  
2. Primary: LangGraph README / checkpoint docs via DeepWiki cites (Tier A when reading README concepts: durable shared state).  
3. **CONFIRMED:** multi-actor apps share typed state across steps — analogous *shape* to our Stage-4 shared evidence pool × many writers.  
4. **UNRESOLVED:** any numeric warn threshold for that pool — LangGraph does not prescribe 80k.

---

## 3. BFS / DFS traversal log (prompt 11)

### Concept seeds (from L2/L2b SoR)

- Merged Stage-4 shared pool × taxonomy fan-out vs Stage-1 slice max  
- Chars/N vs real tokenizer  
- Multi-agent **input** capacity warnings (returns omitted)  
- Warn-threshold calibration practice  

### BFS ring 1 (titles / abs / docs headings)

| Node | Tier | Claim-bearing? | Score |
|------|------|----------------|-------|
| arXiv:2604.01664 ContextBudget (spring) | A | Y | high |
| arXiv:2607.24653 Kimi K3 (summer) | A | Y | high |
| arXiv:2605.00410 Agent Capsules (spring) | A | Y | med |
| arXiv:2508.04903 RCR-Router (2025-08, demoted) | A | Y | low (season) |
| litellm Agent Iteration Budgets docs | A | Y | high |
| deepwiki litellm / langgraph | C | N (nav) | — |
| ArchAgent arXiv:2601.13007 | A | Y for *partitioning* | low for *threshold number* |

### DFS seeds → outcomes

| Claim | Path | Verdict |
|-------|------|---------|
| Explicit remaining-budget signal before append is the right *shape* for capacity tools | ContextBudget §3.1 | **CONFIRMED** — our Stage-0/L2b preflight warns before full Stage-4; keep measuring |
| Long-horizon agent/coding + large context are first-class at frontier (K3) | arXiv:2607.24653 abs | **CONFIRMED** — raises feasibility of mid-size measured runs; **does not set our 80k** |
| Merged/shared prompts can hurt if you stuff more context | Agent Capsules §7.4 (abs/HTML) | **CONFIRMED** — reinforces partial_proxy / measured honesty; not a default |
| Production stacks enforce **measured** spend/iteration caps | LiteLLM docs | **CONFIRMED** — change defaults only from measurement |
| 80000 is the correct chars/N shared-pool warn for this product | — | **UNRESOLVED** — no Tier-A source; **retain stated guess** until mid-size run |

### Stopping rule

- Two BFS rings after the seeds above added **no new claim-bearing nodes** that could justify a numeric default change (saturation on *threshold number*).  
- Remaining frontier is **measurement**, not more papers.

### Frontier (resume shape)

| Node | Why unexpanded | Score |
|------|----------------|-------|
| Mid-size spring-boot target run_dir with summaries.json + interview_answers.json + spring_signals.json | **Required** to change default; not available in-repo | critical |
| Real tokenizer calibration vs chars/N | CONSTRAINTS known open; orthogonal to picking 80k today | med |
| Agent Capsules full §7.4 reproduction against LangGraph | Interesting; would not produce our threshold | low |
| FActScore arXiv:2305.14251 | On-topic for *claim tagging*, off-topic for capacity threshold | reject for this note |

---

## 4. Mapping back to this repo

| Our field | Prior-art lesson | Action |
|-----------|------------------|--------|
| `partial_proxy_pre_stage4` | Budget-free / proxy-only is dangerous | Keep Stage-0 proxy labeled; do not claim closed |
| `measured_stage4_inputs` | Measure before you set B; long-context models make mid-size runs more feasible (K3) | Keep CLI; run on mid-size repo before changing default |
| default `80000` | Stated guess; LiteLLM-style caps come from ops measurement; 1M window ≠ warn default | **Retain** |
| returns omitted | Still true; papers do not close return payloads | Keep `return_payloads_estimated: false` |
| Model routing (future) | K3-class for volume/long-horizon; premium for judgment | Apply only if/when multi-model routing exists — not a threshold change |

Anti-band-aid (`rel-partition-bounds-fanout`): raising/lowering 80k to silence warnings **without** measured shared-pool on a real run would fail the Fail-if. This note **refuses** that.

---

## 5. Exit criteria for a *future* threshold change PR

1. Documented mid-size `<run_dir>` path + measured shared-pool / proxy ratio from `compute_stage4_calibration`.  
2. Proposed N with rationale tied to that measurement (and still warn that returns are omitted).  
3. Update this note’s §0 decision table; STATUS/queue in the same PR.  
4. Do not invent Stage-0 interview token guesses.

---

## 6. Citations

- arXiv:2604.01664 ContextBudget (spring 2026 — Review A)  
- arXiv:2607.24653 Kimi K3 (summer 2026 — Review B)  
- arXiv:2605.00410 Agent Capsules (BFS tertiary, spring 2026)  
- arXiv:2508.04903 RCR-Router (demoted; Aug 2025)  
- https://docs.litellm.ai/docs/a2a_iteration_budgets  
- https://github.com/BerriAI/litellm (55k★, push 2026-07-30)  
- https://github.com/langchain-ai/langgraph (38k★, push 2026-07-30)  
- https://github.com/MoonshotAI/Kimi-K3 (7.5k★, push 2026-07-28)  
- DeepWiki: `BerriAI/litellm`, `langchain-ai/langgraph` (Tier C orientation only)  
- Repo: `src/doc_engine/tools/capacity_preflight.py`, PR #74  
