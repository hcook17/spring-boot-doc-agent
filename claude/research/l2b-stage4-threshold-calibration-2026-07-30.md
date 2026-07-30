# L2b Stage-4 threshold calibration research (2026-07-30)

**Status:** Closed for *default selection* — **retain `--stage4-shared-tokens-warn-threshold` default `80000`**.  
**Not closed:** Stage-4 capacity risk (returns still omitted); mid-size `measured_stage4_inputs` run still required before *changing* the default.  
**Method:** [00-shared-research-standards.md](../steering-prompts/00-shared-research-standards.md) + [11-context-traversal-protocol.md](../steering-prompts/11-context-traversal-protocol.md) (BFS discover → DFS ground).  
**DDIA:** `rel-partition-bounds-fanout`, `claims-and-status-drift`.  
**SoR for our metric:** on-disk Stage-4 inputs via `capacity_preflight.measure_stage4_shared_pool_tokens` / CLI `--summaries-file` (PR #74). Numeric `*_upper_bound_*` fields remain warn-threshold names only.

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

### Review B — RCR-Router (arXiv:2508.04903)

| Field | Value |
|-------|--------|
| Abs | https://arxiv.org/abs/2508.04903 |
| Mechanism | **Role-aware context routing** for multi-agent LLMs: select memory subsets under a **strict per-agent token budget** B; iterative routing; reports quality vs B. |
| Tier | **A** (primary: abs + HTML) |
| Maps to L2b? | **Partially.** Confirms multi-agent systems need **per-dispatch input budgets**, and that quality gains **saturate** as B grows (diminishing returns). |
| Does **not** map | Reported B ∈ {512, 1024, 2048, 4096} are **memory-retrieval** caps in QA routers — not chars/N of merged summaries×14 writers. |

**CONFIRMED claims (B):**

1. Static/full-context routing wastes tokens — abs.  
2. Under varying B, consumption grows with B while quality improves **sublinearly** and **saturates** (paper discusses effect of token budget constraints; gains flatten beyond larger B such as 2048 in their tables).  
3. Multi-agent load is not “one quiet Stage-1 slice ⇒ Stage-4 fine.”

**REFUTED for our default:**

- Copying B=2048 or B=4096 into `--stage4-shared-tokens-warn-threshold` — **wrong unit / wrong SoR**.

### BFS-discovered tertiary (not one of the two required reviews)

**Agent Capsules** (arXiv:2605.00410) — multi-agent pipeline compound vs fine execution; **controlled negative result** that injecting *more* context into a merged call can **worsen** compression/quality; compares to LangGraph 14-agent pipeline on tokens. Used as BFS ring fuel → DFS seed for “merged shared pool ≠ free lunch.” Does **not** replace Review A/B.

---

## 2. GitHub comparators (00 bar)

| Repo | Stars (2026-07-30) | `pushed_at` | Adoption signal | DeepWiki | Role |
|------|-------------------:|-------------|-----------------|----------|------|
| [BerriAI/litellm](https://github.com/BerriAI/litellm) | **55116** | 2026-07-30 | Gateway/SDK widely deployed; docs + PyPI; continuous pushes | Indexed (2026-07-29) — **Tier C only** | Primary: **budget enforcement** as product feature |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | **38518** | 2026-07-30 | Default multi-agent orchestration stack; cited by Agent Capsules | Indexed (2026-07-02) — **Tier C only** | Secondary: **fan-out / shared state** mental model |
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
| arXiv:2604.01664 ContextBudget | A | Y | high |
| arXiv:2508.04903 RCR-Router | A | Y | high |
| arXiv:2605.00410 Agent Capsules | A | Y | med |
| litellm Agent Iteration Budgets docs | A | Y | high |
| deepwiki litellm / langgraph | C | N (nav) | — |
| ArchAgent arXiv:2601.13007 | A | Y for *partitioning* | low for *threshold number* |

### DFS seeds → outcomes

| Claim | Path | Verdict |
|-------|------|---------|
| Explicit remaining-budget signal before append is the right *shape* for capacity tools | ContextBudget §3.1 | **CONFIRMED** — our Stage-0/L2b preflight warns before full Stage-4; keep measuring |
| Per-agent input budgets show diminishing returns as B grows | RCR-Router budget-effect section | **CONFIRMED** (their metric) — **does not set our 80k** |
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
| `measured_stage4_inputs` | Measure before you set B | Keep CLI; run on mid-size repo before changing default |
| default `80000` | Stated guess; LiteLLM-style caps come from ops measurement | **Retain** |
| returns omitted | Still true; papers do not close return payloads | Keep `return_payloads_estimated: false` |

Anti-band-aid (`rel-partition-bounds-fanout`): raising/lowering 80k to silence warnings **without** measured shared-pool on a real run would fail the Fail-if. This note **refuses** that.

---

## 5. Exit criteria for a *future* threshold change PR

1. Documented mid-size `<run_dir>` path + measured shared-pool / proxy ratio from `compute_stage4_calibration`.  
2. Proposed N with rationale tied to that measurement (and still warn that returns are omitted).  
3. Update this note’s §0 decision table; STATUS/queue in the same PR.  
4. Do not invent Stage-0 interview token guesses.

---

## 6. Citations

- arXiv:2604.01664 ContextBudget  
- arXiv:2508.04903 RCR-Router  
- arXiv:2605.00410 Agent Capsules (BFS tertiary)  
- https://docs.litellm.ai/docs/a2a_iteration_budgets  
- https://github.com/BerriAI/litellm (55k★, push 2026-07-30)  
- https://github.com/langchain-ai/langgraph (38k★, push 2026-07-30)  
- DeepWiki: `BerriAI/litellm`, `langchain-ai/langgraph` (Tier C orientation only)  
- Repo: `src/doc_engine/tools/capacity_preflight.py`, PR #74  
