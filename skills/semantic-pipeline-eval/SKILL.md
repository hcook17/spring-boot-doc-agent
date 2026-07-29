---
name: semantic-pipeline-eval
description: Semantically evaluate a completed document-spring-repo pipeline run's actual output quality — not just its shape. Samples [Evidenced] claims and checks the cited file:line really supports the claim, flags [Confirmed] tags with no matching interview_answers.json entry, checks doc-writer files for contradictions against the merged architecture diagram or each other, and validates Mermaid diagram syntax. Complements scripts/test_pipeline_stages.py, which only checks structural shape (tag grammar, citation resolvability, JSON schema) and explicitly does not judge truthfulness. Use after a real pipeline run, pointed at its PIPELINE_ARTIFACTS_DIR, when you want a quality/hallucination check beyond mechanical validation — not as a replacement for test_pipeline_stages.py, which should still run on every change to the five agent prompts.
---

# Semantic pipeline evaluation

## What this is and isn't

`scripts/test_pipeline_stages.py` already proves an `[Evidenced — path:line]` citation *resolves* to a real file/line, that `file-summarizer`/`gap-analyzer` output matches its required JSON shape, and that architecture-diagram node labels trace back to real names. It deliberately never judges whether the claim next to a resolved citation is actually *true*, whether a `[Confirmed — interview, <date>]` tag is really backed by a real interview answer, or whether two doc-writer files quietly disagree with each other. Those are genuine semantic-judgment tasks, not shape checks — this skill's job, not a re-implementation of that script's.

Two of the four checks below only *sound* semantic and are actually mechanical — they're handled by `scripts/semantic_eval_helpers.py`, not by you:
- unresolved `[Confirmed]` tags (no matching `interview_answers.json` entry)
- Mermaid syntax findings (unbalanced brackets/subgraph-end/quotes, and edge endpoints that reference a node never labeled anywhere in the diagram — `find_undefined_node_refs()`, a purely structural check, deliberately distinct from `test_pipeline_stages.py`'s `find_untraceable_nodes()`, which checks whether an *existing* label traces back to a real file/class name)

Run that script first (Step 1). Everything after that — evidenced-claim truthfulness, cross-doc contradiction, and the final semantic confirmation of the mechanical script's hallucination candidates — is your own judgment, scoped by the rubric below, not open-ended review.

## Prerequisites

A completed `document-spring-repo` run's output directory, same `PIPELINE_ARTIFACTS_DIR` convention `test_pipeline_stages.py`'s opt-in real-artifacts pass already uses:
- `interview_answers.json`
- `docs/*.md` (the fourteen doc-writer outputs, or however many exist)
- `docs/architecture.md` (or a file containing a fenced ` ```mermaid ` block) — the merged diagram
- the original target repo's path, to re-read cited `file:line` content (mirrors `PIPELINE_ARTIFACTS_TARGET_REPO`)

## Step 1 — mechanical pre-pass

From a **product monorepo checkout** (not `${CLAUDE_PLUGIN_ROOT}`):

```bash
python3 scripts/semantic_eval_helpers.py <artifacts_dir> --out mechanical_findings.json
```

**Do not** invoke deterministic tools via the plugin install tree (no `scripts/` under the marketplace plugin root).

This produces `unmatched_confirmed_tags_by_file` (candidate hallucinated `[Confirmed]` tags — a worklist, not a verdict; a genuine paraphrase can score low overlap too) and `mermaid_syntax_findings`. Read `mechanical_findings.json` before continuing — it narrows what Steps 2-4 actually need to look at.

## Step 2 — evidenced-claim sampling rubric

Read `${CLAUDE_PLUGIN_ROOT}/skills/semantic-pipeline-eval/references/eval-rubric.md`'s "Evidenced-claim truthfulness" entry before starting.

**Sample size per doc file — proportional by default, and configurable:**

```
N = clamp(round(evidenced_claim_count_in_file * 0.15), min=3, max=12)
```

The floor (3) guarantees every doc file gets a real spot-check even if it has only a handful of `[Evidenced]` claims; the ceiling (12) bounds worst-case cost on citation-dense files (`database.md`, `authorization.md`). All three numbers (0.15 ratio, floor 3, ceiling 12) are parameters, not hidden constants — override them for a given run if the user asks (e.g. "sample every claim in `authorization.md` this time," "use a 0.05 ratio on a huge doc set").

**Before sampling, project this pass's own cost — do not exempt this skill from the same scalability discipline it's partly built to enforce elsewhere.** Compute, using the product checkout's `partition_repo` token estimator (the same one `capacity-preflight` uses — not a second implementation; import from the installed package or monorepo `scripts/`, never via the Claude plugin install tree):
- `total_claims_sampled` = sum of per-file N above
- projected tokens ≈ `total_claims_sampled` × (avg cited file:line window + surrounding lines + claim text, estimated via `partition_repo.estimate_tokens`-style chars/N) + Step 3's cross-doc-pass overhead (proportional to total doc-set size) + Step 4's per-flagged-item confirmation cost (count of Step 1's mechanical findings × a per-item estimate)

Print this projection to the user before sampling starts, the same way `capacity-preflight` surfaces its own numbers before a full run — non-blocking, with the same "reduce N or scope to specific files" escape hatch if the projection looks large.

**Judgment procedure per sampled claim:** read the cited `file:line` ± a few lines of context from the target repo, compare against the claim's actual wording, classify as `Supported` / `Overstated` / `Contradicted` / `Citation irrelevant`.

## Step 3 — cross-doc/cross-diagram contradiction pass

Read the merged architecture Mermaid block plus its Discrepancies section, then check each doc-writer file's factual claims (component names, data-flow direction, entity/table names) against it and against each other — e.g. does `database.md`'s table list match `architecture.md`'s data-layer nodes; does `authorization.md`'s stated auth mechanism match what `integrations.md` implies for the same endpoint. Flag disagreements as `Contradiction` findings, tagged with both source locations. Read `eval-rubric.md`'s "Cross-doc contradiction" entry — it has a worked false-positive example (two docs describing the same thing from different angles is not automatically a contradiction).

## Step 4 — semantic confirmation of mechanically-flagged hallucination candidates

For every Step 1 finding in `unmatched_confirmed_tags_by_file`, do a final judgment pass before calling it a true hallucination: the mechanical script's word-overlap check can false-positive on a genuine paraphrase. Reclassify each as `Confirmed hallucination` or `False positive — paraphrase, not hallucination`.

## Step 5 — human sign-off routing

Sign-off is **not** limited to items you flagged as ambiguous. Two separate lanes:

1. **Escalated review** — every `Contradicted`, `Citation irrelevant`, `Confirmed hallucination`, and Mermaid-syntax-error finding is always routed to the user for explicit sign-off.
2. **Confidence spot-check** — additionally, pull a small random sample of the claims *you* classified `Supported` (i.e., confident, non-escalated) for human review:

   ```
   spot_check_n = clamp(ceil(0.10 * count_of_supported_findings), min=3, max=12)
   ```

   Same floor-and-ceiling shape as Step 2's N — not a bare `min(3, ...)`. A `min(3, ceil(0.10*count))` is a *ceiling* that locks the spot-check at exactly 3 for any count of 30 or more, which is the opposite of what "catch a systematic bias at scale" requires: a 500-finding run and a 20-finding run would get an identically-sized check. A bare `max(3, ...)` fixes that but leaves cost unbounded on very large runs — reintroducing, in the spot-check lane, the exact "no cap on fan-out" pattern `capacity-preflight` exists to close in the main pipeline. The clamped form (floor 3, grows proportionally, capped at 12, mirroring Step 2's N exactly) is the one to use.

   Rationale: if your own judgment has a systematic bias (e.g., consistently marking a certain claim pattern `Supported` when it's actually borderline), routing only your own self-flagged escalations can never catch that — you won't escalate what you're confidently wrong about. This spot-check is the mechanism that catches a consistently-wrong judgment pattern before it passes unreviewed.

## Output

Write `semantic_eval_report.md` (or emit inline if the user didn't ask for a file), with sections mirroring Steps 1-4, each finding tagged `[Supported]` / `[Overstated]` / `[Contradicted]` / `[Citation irrelevant]` / `[Mermaid syntax error]` / `[Confirmed hallucination — needs human review]`, plus a **sample coverage** note showing, separately:
- how many of how many total `[Evidenced]` claims were actually sampled (Step 2) — this is not exhaustive
- how many `Supported` verdicts were additionally spot-checked by a human (Step 5, lane 2) — do not conflate this with the escalation lane

## What this deliberately does not do yet

- No exhaustive claim-checking — sampling only, cost-bounded by design (see Step 2's projection).
- No automated re-run/gating decision — this produces a report for a human to act on, not a pass/fail gate.
- No new dependency — no Mermaid-rendering library, no LLM-judge framework, no schema-validation library for `interview_answers.json` (that gap is `claude/steering-prompts/02-pluggability-research-prompt.md`'s, not this skill's to close).
- Does not replace `scripts/test_pipeline_stages.py` — run both; that script should still run on every change to the five agent prompts (and in CI).
