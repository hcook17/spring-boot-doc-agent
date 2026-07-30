---
category: Architecture maturation — scoping and phase plan
status: proposed; mostly not started, but several Phase-0 items were already done or partly done when this was written — see the audit annotations below
date: 2026-07-24
supersedes: nothing; consolidates code-review_4, deep-dive_4, er-model-review_3 (all three live outside this repo — see the note under the title)
artifacts-to-create: scripts/local_ci.sh, .github/workflows/_python-checks.yml, PORTING.md
artifacts-existing: .github/workflows/ci.yml
see-also: claude/research/source-text-vs-bytecode-analysis.md; claude/jpa-hibernate-predicate-vocabulary-survey.md; claude/hibernate-jakarta-fact-verification-2026-07-24.md
revised: 2026-07-24 — Phase 0.1 restructured around CI-convention adoption; C1 now closes by omission. Second revision same day: 1.1.3's predicate vocabulary superseded by the completeness survey; 1.3.2 gains a third reconciliation verdict; Phase 1 sizing flagged for re-estimate; a second constraint-relaxation threshold added (review-raised, untested)
---

# Architecture maturation plan: `spring-boot-doc-agent`

> **Current as of 2026-07-30 (read this first).** Product SoT is **doc-engine** ([`docs/product-architecture.md`](../docs/product-architecture.md)): Stage 0 tools live under `src/doc_engine/tools/`, invoke via `doc-engine` / `python -m doc_engine.tools.*`, Claude plugin is an adapter under `adapters/claude/`.
>
> **§0–1 and the JPA survey are outdated planning text**, not executable specs. The DDIA thesis was revalidated by [`claude/research/fact-store-phase1-decision-memo-2026-07-30.md`](research/fact-store-phase1-decision-memo-2026-07-30.md) (**REFINE**). **Phase 1 = thin dual-emit** (`facts.jsonl` beside `spring_signals.json` per [`research/facts-ledger-schema-2026-07-30.md`](research/facts-ledger-schema-2026-07-30.md)) — **landed in PR #63**; not a walk of this file’s phase checklist. Contested `entity_table_map` remains; maps are not replaced in Phase 1. Next engineering: [`research/adoption-blockers-queue-2026-07-30.md`](research/adoption-blockers-queue-2026-07-30.md).
>
> **Do not** treat Phase 0.1 Elsevier-port deliverables (`PORTING.md`, `scripts/local_ci.sh`, `.github/workflows/_python-checks.yml`) as current work — they were never landed and are superseded by portable-kernel CI in `.github/workflows/ci.yml`. Path cites that say `scripts/spring_signal_scan.py` (etc.) mean `src/doc_engine/tools/` today. Packaging/hygiene is paused as complete.

Self-contained. Consolidates three independent principal-engineer reviews (`code-review-spring-boot-doc-agent_4.md`, `deep-dive-spring-boot-doc-agent_4.md`, `er-model-review-spring-boot-doc-agent_3.md`) plus the prior-art investigation into a single sequenced plan.

> **[Reference audit — 2026-07-24]** The three reviews above, `comparable-tools-benchmark.md` (§0 "Keep"), and the prior-art investigation **are not in this repo** and never have been — `find`/`git log` turn up nothing for any of them at any commit. Like the research files named in `claude/steering-prompts/00-shared-research-standards.md`, they live in the Claude project "Plugin For Asynchronous Documentation Creation." They are cited here as evidence, so a reader following them from a repo checkout dead-ends; ask for a copy rather than assuming they were deleted.
>
> Two more references were **wrong rather than external**, and are corrected in the frontmatter above:
> - `claude/archunit-scanner-scoping-2026-07-23.md` → the real file is **`claude/research/source-text-vs-bytecode-analysis.md`** (same subject, same augment-vs-replace fork). Nothing matching `*archunit*` exists anywhere in the tree. §"Thresholds" below still cites the old name inline.
> - The two Hibernate documents were cited by *re-worded title with `.md` appended*, not by path. Their real paths are **`claude/jpa-hibernate-predicate-vocabulary-survey.md`** and **`claude/hibernate-jakarta-fact-verification-2026-07-24.md`** — both in-repo and readable. (The survey itself cites its companion by correct repo path, so the convention was already established; this document just didn't follow it.)
>
> `PORTING.md`, `scripts/local_ci.sh`, `.github/workflows/_python-checks.yml`, `scripts/pipeline_validators.py`, `claude/adr/` and `.gitattributes` are **deliverables this plan creates**, not existing files — the frontmatter now says so, and several are referenced in present tense below ("see `PORTING.md`", "`PORTING.md` is the checklist"). `scip.proto` and `java_gradle_build_sonar_qualitygate.yml` are external (Sourcegraph's SCIP, and the Elsevier org) and correctly so.

## 0. The architectural reframe

The fourteen generated documents are **materialized views** over a **fact store derived from the repository**, which is the **system of record** (DDIA 2e Ch1, "Systems of Record and Derived Data"; Ch4/Ch13, materialized views).

There is currently no fact store. There is a flat bag of `{file, line, match, rule_id}` evidence entries plus a unary map `entity_table_map : ClassName → TableName`, and the views are computed directly from those. Once you accept the reframe, the twenty-odd findings collapse into three classes:

| Class | Meaning | Findings |
|---|---|---|
| **A. The store cannot hold the fact** | The record type has no slot for a second citation, an owning side, a qualifier, an uncertainty marker, or a negation | ER (all), D1, D3, D6, D7, H1, D8/D9 |
| **B. Nothing checks the view against the base** | Derivation is neither complete nor validated | D2, D4 |
| **C. Ordinary defects** | Independent of schema; fix on their own merits | C1, C2, H2, H3, M1–M5 |

Class C ships first because two of them are stop-ship. Class A is one schema change. Class B becomes cheap *only after* Class A, because "is there undocumented surface?" is unanswerable until facts are individually addressable.

**Class A is not an exotic mistake.** The Elsevier org's own SQL schema-change workflow contains the same defect in miniature: it sets `HAS_FOREIGN_KEY` and `HAS_CREATE_INDEX` as two independent booleans over the whole diff and never correlates them, so a foreign key added in one migration plus an unrelated index in another passes clean. Two unary flags standing in for a single ≥2-ary predicate — *this* FK, on *this* column, has an index on *that* column. Identical root cause to `entity_table_map`, identical fix shape: carry the pair, not two booleans. Useful as a sanity check that the diagnosis generalizes, and as a concrete example when explaining the rewrite to anyone who has to approve it.

### Why this is a pivot and not a rebuild

**Keep — this is the differentiated part, and no comparable tool has the combination:**

- deterministic scan as ground truth, LLM reasoning layered on top and required to cite it
- the `evidenced` / `confirmed` / `unknown` tri-state (confirmed novel in `comparable-tools-benchmark.md`)
- the live human interview stage — the only stage doing something a script structurally cannot
- two-tier drift (cheap hash filter → targeted structural re-derivation, zero model calls)
- `to_snake_case()` matching Hibernate's actual quirks rather than a plausible approximation
- the never-raise soft-dependency contract for enrichment data

**Scrap — explicitly:**

1. **`entity_table_map` as a data structure.** Non-negotiable. It is a unary function modelling a domain of ≥2-ary predicates. Replace with fact tuples.
2. **`verify_llms_docs.py`'s markdown→`bash -c` execution.** Delete the mechanism; keep the intent.
3. **`_config_keys.py`'s hand-rolled YAML extractor.** Replace with `yaml.safe_load_all`.
4. **`run_ast_grep()`'s `sys.exit` paths.** Replace with a raised exception.
5. **Candidate for scrapping, your call: the whole `claude/llms/pr-N.md` subsystem.** Honest cost/benefit: it has consumed a large share of PRs #9–#21, required a "grace window" hack to escape an infinite regress of its own making, produced the repo's only Critical security finding, and its `ENFORCE = False` means the CI step advertised as a gate is not one.

    **[Audited 2026-07-24 — the range understates the case, and one clause is now stale.]** The real span is **#9–#29**, not #9–#21: add #23 (which flipped `ENFORCE` to `False`), #28 and #29. The "advertised as a gate" clause no longer holds — #29 renamed the step to say "reports … non-blocking" (see 0.4.4 above). But the cost argument is *stronger* than the document claims, on better evidence: `claude/llms/` holds `pr-1.md`–`pr-20.md` and `pr-28.md`, so **`pr-21.md` through `pr-27.md` are missing for seven merged PRs**, plus `pr-29.md` — eight undocumented, silently non-failing because of `ENFORCE = False`. That backlog, not the PR count, is the honest input to this scrap decision. What it buys a *single-contributor* repo is a hand-written restatement of `git show`. The underlying discipline — write-then-verify, born from real device-bridge incidents — is worth keeping. The mechanism is disproportionate to it. Recommend shrinking to a non-executing convention (a doc that *lists* verification commands for a human, never run by CI). Flagged, not decided.

### Principles applied

**DDIA 2e** — Ch1 systems of record vs derived data (derivation must be complete and repeatable); Ch3 triple stores, `(subject, predicate, object)` extended to quads/5-tuples, and many-to-one/many-to-many as the axis a unary map cannot represent; Ch3 schema-on-read (an implicit schema the reader assumes and nothing enforces — precisely what `entity_table_map` is); Ch5 the merits of an explicit declared schema, plus backward/forward compatibility for a format read across versions; Ch6 last-write-wins is lossy conflict resolution; Ch9 formal methods and randomized testing; Ch13 the write path / read path split and "Trust, but Verify" — system models treat faults as binary while reality is probabilistic.

> **[Audited 2026-07-25 against DDIA 2e itself — the frame is right, the claim is half-true, and the half that fails is Ch1's.]** This section names the correct principles; it does not record which of them the system actually satisfies. Measured:
>
> 1. **Derivation is not repeatable — the core Ch1 contract this section quotes.** Ch1's point about derived data is that you can discard it and regenerate it from the system of record. Four of five stages are LLM calls, so two runs over an *unchanged* repository produce different documentation. The **LLM** paragraph below states determinism as a goal ("same facts ⇒ same docs, so drift is attributable to code change rather than model variance") and **nothing measures it**. The consequence is concrete rather than theoretical: when `spring_drift_check.py` reports inputs unchanged but the docs differ, there is no way to tell signal from model variance — the drift-checker is well built for a contract the system does not satisfy. Cheapest first step is a *determinism probe*: run one stage twice on identical input, diff, report the variance as a number. Until that exists, every claim about drift attribution here is unfounded.
> 2. **Ch5 schema discipline stops exactly at the deterministic boundary.** Counted: `spring_signals.json` carries `schema_version` (10 references in the scanner, real versioning discipline) and `run_manifest.json` has an actual JSON Schema file. Every artifact produced by or consumed across an *LLM* stage has none — `groups.json` 0, `summaries.json` 0, `gap_questions.json` 0, and the fourteen docs are prose plus a tag grammar. Their schemas are implicit and validated only by convention in `test_pipeline_stages.py`. `claude/steering-prompts/02-pluggability-research-prompt.md` is precisely this work and is the largest prompt in the repo never picked up. Start with `summaries.json`: three stages consume it.
> 3. **There are two systems of record and only one is durable.** `interview_answers.json` is human input the code cannot regenerate, so the docs derive from the codebase *and* from a snapshot of a conversation. `[Confirmed — interview, <date>]` makes staleness visible, which is honest, but half the provenance graph is unversioned and unreproducible and that is not stated anywhere as an architectural property. It is not obviously fixable — the interview exists because those facts are structurally invisible to static analysis — but it should be named rather than implied.
>
> What genuinely does hold, so this reads as an audit and not a complaint: Stage 0 as system of record with the LLM layer required to cite it is Ch1's discipline applied correctly; `[Evidenced — path:line]` is explicit provenance; `spring_drift_check.py`'s two-tier design (cheap whole-file hash filter, then targeted structural re-derivation only for what changed) is textbook change-data-capture over a materialized view; and the tri-state tagging treats uncertainty as a first-class value, which most systems do not.

**SOLID** — SRP: `spring_signal_scan.py` currently owns walking, ast-grep invocation, entity extraction, secret scanning, SQL lineage, and config keys. OCP: adding a fact type today requires edits to the rules YAML, `_extract_entity()`, the taxonomy, and the doc-writer prompt; it should require registering a rule and an emitter. ISP: every doc-writer receives the whole evidence bucket rather than its slice — simultaneously a token-cost and a hallucination-surface problem. DIP: `resolve_jpql_to_lineage()` binds concretely to `entity_table_map`; it should depend on a `FactStore` interface, which is what later permits swapping in migration-derived facts without touching lineage code.

**LLM** — grounding by construction (the writer receives facts and fact-ids, never raw code, and may not assert without a fact-id); uncertainty as a first-class value; determinism (same facts ⇒ same docs, so drift is attributable to code change rather than model variance); context isolation (siblings share nothing, so anything global must be threaded explicitly — already learned in `architect-merge`).

---

## Phase 0 — Stop crashing, stop lying

**Goal:** nothing executes model-authored shell; nothing hangs; nothing publishes a confidently wrong fact.
**Sizing:** ~1 week. **No architectural change.** Every item here survives Phase 1 untouched.
**Exit criteria:** hostile-fixture test rejects shell metacharacters; Hypothesis runs ≥10k examples clean on `build_groups`; zero `available: true` on ambiguous or truncated input.

### 0.1 CI foundation, and closing the C1 exposure by omission
The C1 fix and CI adoption turn out to be **the same task**, which collapses two work items into one. You do not rewrite `verify_llms_docs.py` to make CI safe — you build the new workflow **without it**. The exposure closes on the day the workflow lands, unconditionally, and independently of whether the `claude/llms/` convention survives at all.

Mirrors the Elsevier org's existing GitHub Actions conventions so the eventual port is near-zero-diff. Three files plus a porting note; see `PORTING.md`.

- 0.1.1 Land `scripts/local_ci.sh`, `.github/workflows/_python-checks.yml`, `.github/workflows/ci.yml`, `PORTING.md`. Structure copied from the org: reusable `workflow_call` invoked by a thin caller, SHA-pinned actions (SHAs lifted verbatim from the org's own files so the port introduces no new pins to review), explicit minimal `permissions:`, job-level `timeout-minutes`, and the validate → `continue-on-error` → build-comment-file → `readFileSync` → post → `exit 1` pattern from their YAML-validation workflow.
- 0.1.2 **`local_ci.sh` is the single source of truth; the workflow calls the script rather than restating the commands.** Two copies of "what CI does" is the identical drift failure mode `CONSTRAINTS.md` already tracks for docs versus code, and this repo has a poor record with it. This also guarantees the local loop and CI cannot disagree.
- 0.1.3 **The C1 exposure is closed by omission.** The new workflow never invokes `verify_llms_docs.py`: no `GH_TOKEN` in scope, no shell, no markdown parsing anywhere in CI. Do not re-add it.
- 0.1.4 `zizmor` and `actionlint` as gates (~~already wired into `_python-checks.yml`~~ **[Corrected — audited 2026-07-24: nothing is wired. `.github/workflows/` contains exactly one file, `ci.yml`, and `_python-checks.yml` does not exist. This parenthetical also contradicted 0.1.1 directly above, which lists that same file as something to *land* — an internal inconsistency, not just staleness. Neither `zizmor` nor `actionlint` appears in `ci.yml`.]**). Point them at the org's five workflows too — the Sonar-token-on-the-command-line finding is precisely what zizmor exists to catch.
- 0.1.5 **Only now** decide the fate of the `claude/llms/` subsystem (Scrap item 5). If scrapped, 0.1.6 disappears. If kept in reduced form, it must be a human-read convention that CI never executes.
- 0.1.6 **Conditional on 0.1.5 keeping the script:** rewrite with `shlex.split()` → `subprocess.run(argv, shell=False)`, validate `argv[0] ∈ {git, gh}` **and** the subcommand token against a read-only allowlist **and** reject URL-valued arguments — the disclosed CVE against `claude-code-action` was exploitable through `gh issue view` with a URL argument, and the vendor fix was an argument-validating wrapper. Regression fixture: a `pr-N.md` containing `git log -1; touch /tmp/pwned` must be **rejected**, asserting `/tmp/pwned` does not exist.

**Two-track note.** Track A (now, personal machine): `runs_on: ubuntu-latest`. `hcook17/spring-boot-doc-agent` is a private repo on github.com with free Actions minutes and an already-green run — only the *Elsevier* runners are out of reach, not CI itself. Track B (later, org): one input change, or a documented four-line edit if the org requires the runner-group map form. Expressions in `runs-on` are officially supported for strings and arrays; templating the whole `group:` map is undocumented and community reports conflict, so that path stays unverified until tested against a real org runner. Day to day, `bash scripts/local_ci.sh all` needs no Docker, no runner, and no network, and works in Git Bash on Windows. `act` (v0.2.89) is available but needs Docker Desktop and its default images are not runner-faithful — not worth the setup here.

**Org feedback to raise separately** (not plugin work; recorded in `PORTING.md`): the Sonar token is passed both as an env var and as `-Dsonar.token=` on the command line, where it is visible in the process table on a shared runner; `tj-actions/changed-files` is the CVE-2025-30066 action, correctly SHA-pinned but worth confirming the pin is post-remediation; and the SQL schema-change workflow greps the whole diff rather than added lines, so *removing* a foreign key trips the failure.

### 0.2 Kill the unbounded loop (C2)

> **[Resolved before this plan was written — audited 2026-07-24]** The loop was already killed. `build_groups()` carries an explicit zero-progress guard at `scripts/partition_repo.py:248-257`, added by `5b8e8c8` and in `main` since **PR #1** (`0b7b7de`) — well before this document's own date. A named regression test pins the repro: `test_strict_mode_zero_progress_guard_prevents_infinite_loop`, `scripts/test_partition_repo.py:130`. So the framing "stop-ship" / "Today the preflight tool hangs" (0.2.5) was already false when written.
>
> **Do not apply 0.2.1 as specified — it is weaker than what shipped, and its assert is harmful.** `reversed(closed_group[1:])` guarantees only that the carry is a *proper subset*; with 2+ files the carry can still be large enough that the triggering file doesn't fit, which is the actual hang condition. The shipped guard keys on that condition directly (`carried == current_tokens and carried + tok > max_tokens`). Applying `[1:]` on top would also silently drop the first file from overlap eligibility at *every* seam, changing partitioning behaviour for no correctness gain. And `assert len(carry) < len(closed_group)` would fire on the single-file-group case the guard handles by emptying the carry — it is a tautology after the guard and a crash before it.
>
> **Still genuinely open:** 0.2.2–0.2.4 (Hypothesis property tests, the `@example` pin, the `RuleBasedStateMachine`). `hypothesis` is not in `requirements.txt`. 0.2.3 is partly satisfied by the unit test above. The state-dependence argument for 0.2.4 stands.

- 0.2.1 `carry_forward()` must never carry the entire closed group — iterate `reversed(closed_group[1:])` — and assert `len(carry) < len(closed_group)` afterward. Forward progress becomes unconditional. **[Superseded — see the note above. The shipped guard is the better fix; this prescription should not be applied.]**
- 0.2.2 Add Hypothesis property tests: termination via `@settings(deadline=...)`; invariant 1, every input file appears in ≥1 group; invariant 2, every group ≤ cap unless it holds exactly one oversize file.
- 0.2.3 Pin the known five-integer repro with `@example` so it can never regress.
- 0.2.4 Add a `RuleBasedStateMachine` for the accumulate/close/carry sequence — the bug is state-dependent, which is why line coverage executed the guard and still missed it (Ch9).
- 0.2.5 Add a `max_group_tokens` warning dimension to `compute_preflight()`; emit oversize files in a dedicated array (M4). ~~Today the preflight tool hangs on precisely the repos it exists to warn about.~~ **[Partially stale — audited 2026-07-24.]** The warning dimension is genuinely absent and still worth adding: `compute_preflight()` (`scripts/capacity_preflight.py:133`) takes only `group_warn_threshold`, `fanout_warn_threshold` and `references_tokens_warn_threshold`, and its report carries no oversize-files array. (The `max_tokens_per_group` key at `:201` is the echoed *input* cap, not a warning.) **But the "hangs today" justification is false** — `compute_preflight()` reaches `build_groups()` via `_load_or_build_groups()` (`:91`), i.e. the same guarded function as 0.2, so it cannot hang on this path. Keep the item; drop the urgency framing.

### 0.3 Truthfulness triage — degrade, do not fix (H1, H2, D1)
The elegant move: convert *confidently wrong* into *honestly silent* without touching the schema. Cheap, urgent, and not throwaway — the degrade paths survive Phase 1 as the `contested` route.
- 0.3.1 **H1:** detect simple-name collision across packages; set a sentinel so `resolve_jpql_to_lineage()` returns `available: false, reason: "ambiguous entity name across packages"`; warn on stderr. Also sort the map assignment for determinism — today the winner depends on multithreaded ast-grep match order. **Note (survey):** once Phase 1 lands, this check must key on the persistence unit as well — see 1.1.6. A multi-datasource repo with two correct, intentionally-parallel mappings is not ambiguous, and this check will call it so.
- 0.3.2 **H2:** detect Java text blocks (`"""`) and `+` concatenation; omit `query` and set an explicit reason. Never publish a truncated query as `available: true`.
- 0.3.3 **D1:** widen the `persistence__entity` rule's `has:` clause to `any: [marker_annotation, annotation]` so `@Entity(name = "...")` stops being *absent*. Partial is strictly better than invisible: an absent entity produces no citation, so drift can never surface it and the omission is permanent.
- 0.3.4 Add fixtures for all three. The current suite pins counts against fixtures containing only the bare annotation form, which is why these pass CI today.

### 0.4 Harness and hygiene
- 0.4.1 `.gitattributes` with `* text=auto eol=lf`, then `git add --renormalize .` (M1). Do this before anyone scans on one platform and drift-checks on another — `compute_file_signature()` hashes raw bytes, so CRLF churn reports every file changed.
- 0.4.2 Replace `sys.exit(1)` in `run_ast_grep()` with `AstGrepInvocationError`; catch in all three `main()`s; in `tier2_recheck_file`, catch per-file and mark `unknown_recheck_failed` rather than aborting a whole run (M2). **[Partly resolved — audited 2026-07-24.]** The harder half shipped, under a different name and in a different function: **`AstGrepNotFoundError`** (`scripts/spring_signal_scan.py:489`), raised from **`find_ast_grep()`** (`:509`), and all three `main()`s already catch it — `spring_signal_scan.py:849`, `spring_drift_check.py:780`, `capacity_preflight.py:239`. There is no `AstGrepInvocationError`; don't add a second class, extend the existing one. **Residual, still open:** `run_ast_grep()` itself keeps two `sys.exit(1)` calls (`:552` non-zero exit, `:557` bad JSON), and `tier2_recheck_file` (`spring_drift_check.py:611`, called unguarded at `:727`) still aborts the whole run rather than marking `unknown_recheck_failed` — that string appears nowhere in the repo.
- 0.4.3 Add `syrupy` golden snapshots of `spring_signals.json` and each of the fourteen docs. **This is the regression net that makes Phase 1 safe** — without it you are re-shaping the core data structure with no way to prove equivalence.
- 0.4.4 `.vs/` to `.gitignore` + `git rm -r --cached`; correct the stale `UNLICENSED` claim in `README.md:92`; rename or enforce the CI step whose label claims a gate that `ENFORCE = False` disables.

  **[Audited 2026-07-24 — two of three now done, one still fully open.]**
  - `.vs/` — **still open, exactly as described.** `.gitignore` has `.vscode/` (line 4) but no `.vs/`, and five `.vs/` files are tracked (`VSWorkspaceState.json`, `slnx.sqlite`, a `FileContentIndex/*.vsidx`, `v17/.wsuo`, `v17/DocumentLayout.json`).
  - `UNLICENSED` — **[Resolved — PR #29, `add3083`]** `README.md` now states `plugin.json`'s license is MIT, matching the root `LICENSE`. Note the pointer `README.md:92` is stale in two ways: the content is fixed, and the sentence moved to `README.md:94` (`:92` is now the `## Before you use this for real` heading).
  - CI step label — **[Resolved — PR #29, `add3083`, via the "rename" branch]** the step is now `check_llms_coverage.py (reports merged PRs with no claude/llms/pr-N.md; non-blocking)` with a comment explaining the rename and when to revert it. `ENFORCE = False` is unchanged at `scripts/ci/check_llms_coverage.py:52` — deliberately, since "rename **or** enforce" is satisfied and flipping the toggle is a policy call tied to backfilling `pr-21..27.md`.

---

## Phase 1 — The fact store (the pivot)

**Goal:** one addressable, append-only, n-ary fact record capable of holding every fact the domain actually has.
**Sizing:** ~2–3 weeks **— flagged for re-estimate, see the note below. This is the work.**
**Exit criteria:** every Phase 0 golden snapshot reproducible from v2 facts; a fixture exercising `SINGLE_TABLE`, `@SecondaryTable`, `@JoinTable`, and a cross-package name collision produces correct or explicitly-contested output in all four cases.

> **Sizing re-estimate required (2026-07-24).** The ~2–3 week figure predates the completeness survey. That survey adds at least three cross-file derived rules beyond what 1.4 originally scoped (`@FilterDef`↔`@Filter` name binding, persistence-unit-to-package binding, `@Any` discriminator target resolution), and the base/derived split in 1.6 carries stratification, termination and incremental-recomputation obligations that were not costed at all. Re-estimate before committing to a date; do not treat 2–3 weeks as still holding.

### 1.1 Design the record
- 1.1.1 Shape: `{subject, predicate, object, qualifiers{}, citations[], confidence, derived_from[], layer}`. Model on SCIP's `Relationship` (read `scip.proto` — smallest legible template for a provenance-carrying relational code fact) plus Datomic's provenance dimension.
- 1.1.2 It **must** support the three things impossible today: ≥2 citations on one fact, an owning-side qualifier, and an uncertainty/negation marker (a fact asserting a table does *not* exist, for the `TABLE_PER_CLASS` phantom).
- 1.1.3 **Predicate vocabulary — superseded.** The illustrative list formerly here (`MAPS_TO_TABLE`, `MANY_TO_ONE`, …) was a sketch, not a survey. Use the closed, version-pinned vocabulary in **`Closing the JPA/Hibernate Predicate Vocabulary: A Bounded Completeness Survey for Static Extraction.md`**, Stage 1 — roughly thirty predicates across five effect categories, including the **row-visibility** family (`RESTRICTED_BY`, `FILTERED_BY`, `SOFT_DELETED_BY`, `IS_IMMUTABLE`, `CUSTOM_SELECT/INSERT/UPDATE/DELETE`, `COMPUTED_BY`, `SYNCHRONIZES_WITH`) that the sketch omitted entirely. Row-visibility predicates change which rows a repository sees without changing which tables exist, so the arity fix alone does not surface them.
- 1.1.4 Add `schema_version`. **This is a cross-version data contract** — `spring_drift_check.py` reads the previous run's output, so a schema change today silently corrupts drift comparison. Backward/forward compatibility is a real requirement here, not ceremony (Ch5).
- 1.1.5 Single source of truth for the shape: validate against the JSON Schema with `jsonschema` rather than maintaining the parallel hand-written `validate_manifest_shape()` the PR #24 review already flagged as a drift risk.
- 1.1.6 **`persistence_unit` is part of the fact KEY, not a qualifier.** Conflict detection (0.3.1, 1.2.2) keys on identity; in a multi-datasource repo the persistence unit is the disambiguator, so omitting it reports two correct parallel mappings as ambiguous and degrades `contested` exactly where it matters most. And it cannot be deferred: 1.1.4 makes this a cross-version contract and 1.5.2 has the drift checker refuse mismatched baselines, so promoting a qualifier into the key later is a breaking change that invalidates every stored baseline. Nullable, with an explicit `assumed-default` sentinel when the survey's Section B static-determinability test fails.
- 1.1.7 **Vocabulary closed but extensible.** Version the predicate set and reserve an `UNKNOWN_HIBERNATE_ANNOTATION` catch-all carrying the raw annotation FQN, so an unmodeled construct is recorded rather than dropped. Its downstream disposition is defined — and mandatory — in the survey's Stage 1a: never citable as prose support, admissible only in the 4.1 negative-space section, citation must still resolve under 2.1.4, and a newly-appearing one is a non-gating drift warning feeding a vocabulary-coverage counter.

### 1.2 Emitter layer (OCP)
- 1.2.1 Registry mapping ast-grep rule → fact emitter. Adding an annotation becomes: write a rule, write an emitter. Zero edits to lineage, taxonomy, or prompts.
- 1.2.2 **Append, never overwrite** (Ch6). Two facts on the same `(subject, predicate)` **within the same persistence unit** are both retained and marked `contested`. This structurally eliminates the H1 class rather than patching one instance of it.
- 1.2.3 Deterministic ordering on emit, not only at the end of `scan()`.

### 1.3 Ground-truth reconciliation
- 1.3.1 Add `sqlglot` (pure Python, no build step, no service) to parse Flyway/Liquibase migrations — the *authoritative* schema artifact — into `DEFINES_TABLE` and `FOREIGN_KEY` facts. Parse `CREATE VIEW` as a distinct node type, not as a table.
- 1.3.2 Reconcile JPA-derived against migration-derived facts. **Three verdicts, not two: `{agree, disagree, not-a-base-table}`.** Disagreement produces `contested`, never a silent pick — this converts "three fabricated table names" into "the migrations define one table, the annotations imply three — contested." But constructs that legitimately map to something that is not a base table (`@Subselect`, `@View`, `@MappedSuperclass`, abstract `TABLE_PER_CLASS` roots) must resolve to `not-a-base-table`, a distinct form of *agreement*, or every view-backed entity becomes a false `contested` and erodes trust in the signal. Symmetrically, a `CREATE TABLE` with no entity preimage matching a `@JoinTable`/`@CollectionTable`/`@TableGenerator` name is reconciled, not orphaned. Detection rules and the `@Immutable` anti-pattern to avoid: survey Section C.
- 1.3.3 Close the naming-strategy blind spot (ER §3) with a presence-only check: if any config key set contains `spring.jpa.hibernate.naming.physical-strategy` or `.implicit-strategy`, downgrade every `inferred-default-naming` fact to unconfirmed. Same shape as the existing secrets check — flag the key, never read the value. Also re-anchor `to_snake_case()`'s docstring, which currently cites Hibernate 5.6.7 and a class deprecated in Boot 2.6 and removed in 3.0, on a tool whose target audience is Boot 3.x.
- 1.3.4 **Record the assumed Hibernate/Jakarta baseline per scan.** `@Where` was removed in Hibernate 7.0, so the same source is valid on 6.x and will not compile on 7.x — version is a correctness input, not metadata. Store as a `hibernate_version_assumed` qualifier.

### 1.4 Decompose `spring_signal_scan.py` (SRP)
- 1.4.1 Split into: walker, ast-grep runner, fact emitters, secret scanner, SQL lineage, config keys.
- 1.4.2 `resolve_jpql_to_lineage()` depends on a `FactStore` interface, not on a concrete dict (DIP). This is what makes 1.3.1 a plug-in rather than a rewrite.
- 1.4.3 This decomposition is what makes Phase 3 cheap. Do not skip it to save a week; you will pay it back with interest across eight rule additions.

### 1.5 Migration
- 1.5.1 Dual-emit v1 and v2 for one release; golden snapshots prove equivalence where they overlap.
- 1.5.2 Drift checker reads `schema_version` and refuses a mismatched baseline loudly rather than comparing incomparable structures.
- 1.5.3 Delete v1 only after one real-repo run on v2.

### 1.6 Base facts vs derived facts (EDB / IDB)
Not an optional refinement — without it the negation slot from 1.1.2 ships empty. A per-match emitter (1.2.1) sees one match and cannot see siblings, so `SINGLE_TABLE` subclass suppression (which needs the whole hierarchy) and the abstract-`TABLE_PER_CLASS` phantom check (which needs a class modifier the entity rule does not read) have nowhere to live. The phantom entries then survive into a store that *looks* more rigorous than the map it replaced — the worst available outcome.

- 1.6.1 Tag every fact `layer: base|derived`. Terminology from Datalog's EDB/IDB split, which CodeQL (extensional/intensional) and Glean (raw/derived predicates) both restate; the prior-art investigation already flagged Glean's "derivation is separate from raw facts" and it was not carried forward until now.
- 1.6.2 Implement the derived pass as a stratified fixpoint in pure Python — stdlib only, no service, no new dependency. First rules: `SINGLE_TABLE` subclass-table suppression, `TABLE_PER_CLASS` abstract-root phantom marking, `mappedBy` owning-side resolution, `@FilterDef`→`@Filter` name binding, `@Any` discriminator target resolution, and persistence-unit-to-package binding.
- 1.6.3 Inherited obligations, none skippable: stratify (no cycles through negation), guarantee termination, recompute derived facts when any contributing base fact changes, and never store a derived fact without `derived_from[]` provenance.

---

## Phase 2 — Close the derivation loop

**Goal:** the derived artifacts are complete with respect to the source of truth, and validated against it.
**Sizing:** ~1 week. Depends on Phase 1 — "is there undocumented surface?" is unanswerable until facts are addressable.
**Exit criteria:** an unresolvable citation fails the run; adding a new `@RestController` to a fixture produces a non-zero exit.

### 2.1 Wire the validators (D4)
- 2.1.1 Promote `resolve_evidenced_citations`, `validate_file_summarizer_entries`, `validate_gap_analyzer_questions`, `extract_mermaid_node_labels`, `find_untraceable_nodes` out of `test_pipeline_stages.py` into a shipped `pipeline_validators.py`.
- 2.1.2 Add a Stage 5 gate in `SKILL.md`, same shape as the existing `check_no_secrets_leaked.py` call — which is already wired correctly and is the pattern to copy.
- 2.1.3 Run against the run's real artifacts. Today the default path validates the validators against hand-written synthetic samples; real output is checked only if `PIPELINE_ARTIFACTS_DIR` is set, which is opt-in, manual, and absent from the normal flow.
- 2.1.4 **Hard gate:** any `[Evidenced — path:line]` that does not resolve to a real file and line fails the run. This is the single highest-value automated check in the project and it currently never touches a generated document. Applies to `UNKNOWN_HIBERNATE_ANNOTATION` citations too — they are real matches and must resolve — but per 1.1.7 they can never be the sole support for an evidenced claim.
- 2.1.5 Give `check_no_secrets_leaked.py` and `doc_tag_utils.py` tests and add both to CI — the former is a safety net whose failure mode is silence.

### 2.2 Additive drift (D2)
- 2.2.1 Compute the surface set: facts with no consuming doc citation → emit status `undocumented_surface`.
- 2.2.2 Non-empty ⇒ non-zero exit, mirroring `oasdiff`'s gate contract. No off-the-shelf tool fits the no-build constraint; the interaction model is what to copy, and you already own the `Counter`/multiset primitive.
- 2.2.3 Fix the stdout summary. A report printing only `unchanged` and `confirmed_still_present` reads as "docs are current," which is a stronger claim than the tool can make — and `README.md` tells operators to use exactly that report to decide whether a re-run is warranted.
- 2.2.4 **Ship this as a new target in `scripts/local_ci.sh`, not a new workflow.** Per 0.1.2 the script is the single source of truth; the gate then runs identically on your machine and in CI, and the PR-comment surface is already built (the org's validate → comment-file → `readFileSync` → `exit 1` pattern, adopted in 0.1.1). The org's own SQL schema-change workflow is the closest existing example of this shape — worth reading before writing it.

### 2.3 Retraction semantics
- 2.3.1 A fact present in the previous run, absent now, and still cited in a document is a **retraction** — the citation is stale even though the file may not have changed in a way tier 1 detects. Datomic's assert/retract dimension, and the missing half of drift.

---

## Phase 3 — Breadth on the new schema

**Goal:** the fourteen documents have evidence proportional to their blast radius.
**Sizing:** ~2 weeks, and cheap only because 1.2 and 1.4 made rules pluggable. Writing any of these against the *current* schema produces more citations that resolve and are false.
**Exit criteria:** `authorization.md` cites route-level facts; a repository interface with fifteen `findBy*` methods and no `@Query` produces more than one persistence fact.

- 3.1 **Relationship rules** — `@ManyToOne`, `@OneToMany`, `@OneToOne`, `@ManyToMany`, `@JoinColumn`, `@JoinTable`, `mappedBy`, `@SecondaryTable`, `@Inheritance`, `@DiscriminatorColumn`, `@MappedSuperclass`, `@EmbeddedId`. Zero rules exist for any of these today. `@JoinTable` is literally DDIA's associative table, and it is invisible.
- 3.1a **Row-visibility rules (new, from the survey)** — `@SQLRestriction`/`@Where`, `@SQLJoinTableRestriction`/`@WhereJoinTable`, `@SoftDelete`, `@Filter`/`@FilterDef`/`@ParamDef`, `@Immutable`, `@Subselect`, `@Synchronize`, `@View`, `@SQLSelect`/`@SQLInsert`/`@SQLUpdate`/`@SQLDelete`, `@Formula`, `@DiscriminatorFormula`. These change which rows a repository method sees or writes without changing which tables exist, so nothing in 3.1 surfaces them. `@SoftDelete` in particular means a table's apparent row count and its documented semantics diverge silently.
- 3.2 **Security DSL (D3)** — `requestMatchers`, `hasRole`, `hasAuthority`, `permitAll`, `anyRequest`, `denyAll`, `oauth2ResourceServer`, `httpBasic`, `formLogin`, captured as `(route, verb, role)` triples. Highest priority in this phase: `authorization.md` has the largest blast radius if wrong and currently gets one citation proving a bean exists. If this slips, `doc-taxonomy.md` must state plainly that route-level authorization is interview-derived so the writer cannot tag it evidenced.
- 3.3 **D7 set** — `@Scheduled`, `@Transactional`, Spring Data derived query methods (`^(find|read|get|query|count|exists|delete|remove)By`), `@NamedQuery`, `@Embeddable`, `@Async`, `@EventListener`. Derived query methods first: in most repos they vastly outnumber `@Query`, and `persistence__repository` already matches the interface node their `method_declaration` children hang off.
- 3.4 **D6** — capture `schema=` and `catalog=`; rewrite JPQL-resolved lineage as `schema.table`. Kills the two-naming-conventions-in-one-document bug.
- 3.5 **D5** — `yaml.safe_load_all()` replaces the hand-rolled extractor, behind `try/except ImportError` with the current code as fallback (the same soft-dependency posture already used for `sqllineage`). Fixes multi-document, lists of maps, block scalars, and flow maps at once. Note Kubernetes and Helm manifests route through this same path and are almost entirely lists of maps, so that bug is the normal case there, not an edge case.
- 3.6 **D8/D9 (ISP)** — restrict `type_usage` rules to `field_declaration`/`formal_parameter`; filter `references__import` to first-party packages using the base package already available from `references__package`. Roughly an order-of-magnitude token reduction and fewer duplicate "facts." **Open, from the survey:** this was scoped against a much smaller vocabulary. 1.1.3 now mints ~30 predicates, of which the eight row-visibility ones will be absent in most repos. Decide whether that family rides the same per-writer-slice filter or needs its own suppression pass; until then, do not treat 3.6's token-reduction figure as still holding.
- 3.7 **H3** — choose one hidden-directory policy and apply it to both walkers. Either allowlist `.github` in `dfs_walk` or drop `--no-ignore hidden/dot` from the ast-grep call and delete the unreachable branch.
- 3.8 **M3** strip a leading `ENV|ARG|LABEL` before applying `KEY_VALUE_LINE_RE`; **M5** record `--respect-gitignore` in `spring_signals.json` and have the drift checker read it back, removing the chance of operator error entirely.
- 3.9 Postgres `::` cast fix in `NAMED_PARAM_RE`'s lookbehind; parenthesize `_recheck_entities`.

---

## Phase 4 — Honesty and self-application

**Goal:** the tool's documentation, and its own, describe verified rather than intended behavior.
**Sizing:** ~1 week. 4.1 is the cheapest high-value item in all three reviews and can be pulled forward at any time.

- 4.1 **Negative space.** Every generated document gets a "what static analysis cannot establish here" section, generated *from the fact store's own gaps* rather than hand-written. A generated document with no stated incompleteness reads to its audience as complete. This section is also the only place `UNKNOWN_HIBERNATE_ANNOTATION` facts surface (1.1.7), and where the survey's five interview questions land when unanswered.
- 4.2 **Conditional generation.** A document with zero evidenced facts emits its negative-space section instead of prose. This stops the fixed fourteen-file taxonomy from compelling confident fiction where evidence is absent.
- 4.3 **Dogfood the drift checker on this repo** (the cross-cutting finding). The reviews confirmed four instances of prose winning over reality: `@Entity(name=...)` documented as a lineage nuance when it is a dropped entity; a `.github` branch described in a comment and unreachable; validators described as checking generated docs while checking fixtures; a license documented as `UNLICENSED` after it became MIT. **[Audited 2026-07-24 — the first three still hold; the fourth was fixed in `add3083`, the same PR that first tracked this document. And the count has since grown, not shrunk: `00-shared-research-standards.md` was edited to claim prompts `01`–`12` are all mirrored from the Claude project when only `00`–`06` exist there, and this very document cited five files that aren't in the repo and two under wrong names. The anti-pattern is live enough to keep re-committing, which is the argument for 4.3 being automated rather than audited by hand.]** Concrete stdlib checks: README flags ↔ `parser._actions`; every backticked path exists; the README license claim matches `LICENSE`; comments asserting reachability cross-checked against coverage data.
- 4.4 Add `pydoclint` for docstring ↔ signature drift.
- 4.5 Move long-form rationale out of module docstrings into `claude/adr/` with pointers. `spring_signal_scan.py` opens with ~150 lines of prose before its first import; the reasoning is high quality and worth keeping, but it is a drift surface, and the stale license claim and the dead `.github` branch are the existing proof.

---

## Cross-cutting: LLM contract changes

Not a phase — these land inside Phases 1–3.

- **Grounding by construction.** The doc-writer receives facts and fact-ids, not raw code, and may not assert a claim without a fact-id. This turns 2.1.4's validator from a checker into a contract.
- **Uncertainty is first-class.** Extend the tri-state with `contested` for collisions and JPA-vs-migration disagreement. The tri-state is the project's confirmed novelty; a fourth value is a natural extension, not a redesign. Note `not-a-base-table` (1.3.2) is *not* a fourth uncertainty value — it is a form of agreement and must not be rendered as doubt.
- **Determinism.** Same facts ⇒ same docs. Golden snapshots make model variance detectable and separable from genuine code drift — currently they are indistinguishable.
- **ISP for prompts.** Each doc-writer receives only its slice of the fact store. Cuts token cost and hallucination surface in the same change. See 3.6's open question about the enlarged vocabulary.

---

## Sequencing summary

| Phase | Theme | Size | Blocks |
|---|---|---|---|
| 0 | Stop crashing, stop lying | ~1 wk | Everything |
| 1 | Fact store (the pivot) | ~2–3 wks **(re-estimate)** | Phases 2 and 3 |
| 2 | Close the derivation loop | ~1 wk | — |
| 3 | Breadth on the new schema | ~2 wks | — |
| 4 | Honesty and self-application | ~1 wk | 4.1 pullable anytime |

## Do this before Phase 1

**Run the current pipeline end-to-end against one real service.** `MATURITY_ASSESSMENT.md` states that `capacity_preflight.py` and `run_manifest.py` have only ever run against the small test fixture. Every finding in the three reviews was reproduced against constructed fixtures, which is rigorous but not the same as a real repository. You are about to spend three weeks re-shaping the core data structure on fixture-derived evidence. One real run is the cheapest available de-risking, and it also tests the thesis that matters most: whether the interview stage earns its cost. If it does not, the differentiation argument weakens and the plan should be revisited before Phase 1, not after.

## Thresholds that would change this plan

- **If "never compile the target" is ever relaxed**, jQAssistant becomes a turnkey answer to Phases 1 and 3 — it already scans Java and Spring configuration into a property graph with Cypher constraints, which is structurally exactly what Phase 1 builds. Revisit rather than continue.
- **If this plugin runs *inside* a target repo's own CI, downstream of an existing compile — [review-raised 2026-07-24, UNTESTED].** A narrower relaxation than the jQAssistant one above, and it does not require running anyone's build yourself. Where a repo already builds on every PR under an org-standard workflow (the Elsevier `java_gradle_build_sonar_qualitygate.yml` shape), a `needs:`-gated downstream job can consume the compiled output directly. Four constraints on the mechanism, all load-bearing:
  1. **Consume the plain classes directory, not the bootJar.** `importJar()` exists, but a Spring Boot executable jar is not a plain jar — classes sit under `BOOT-INF/classes`, deps under `BOOT-INF/lib`, and Boot 3.2+ addresses them with a `nested:` URI scheme ArchUnit does not support (TNG/ArchUnit#1224). Use `importPath()` against `build/classes`. Strictly better anyway: `claude/archunit-scanner-scoping-2026-07-23.md` **[corrected 2026-07-24 → `claude/research/source-text-vs-bytecode-analysis.md`; no `*archunit*` file exists in this repo at any commit]** measured the classes-only path as effectively instant against ~70s for a full-classpath import, and 14 of 21 rules are spike-confirmed low-risk on it.
  2. **Use `upload-artifact`/`download-artifact`, not `actions/cache`.** Cache is a best-effort speed optimization subject to eviction — the org pipeline's `fail-on-cache-miss: 'true'` is the tell that it is being used as a delivery channel it does not guarantee. A documentation job that intermittently cannot find its input is worse than one that never had it.
  3. **This is conditional capability for in-CI invocation only**, and therefore an argument for the *augment* side of the augment-vs-replace fork the scoping doc leaves open — never the replace side. The general "point at any Spring Boot repo" contract is unchanged.
  4. **Not free, and not yet costed.** The org's `jar_path` input is described as the jar feeding the Docker image; consuming classes instead means *adding* a second artifact channel to a shared workflow this project does not own. Confirm that is acceptable with whoever owns those workflows before scheduling the work.

  Scope note: this changes the *evidence source* for some Phase 3 rules. It does not touch the Phase 1 record shape — an ArchUnit-derived fact still needs somewhere n-ary to live — so it reorders nothing before Phase 3.
- **If a real target repo shows derived query methods dominating**, 3.3 moves ahead of 3.1.
- **If a real target repo makes heavy use of `@SoftDelete` or `@Filter`**, 3.1a moves ahead of 3.1 — a silently filtered table is a worse documentation defect than a missing relationship, because the reader has no cue that anything is absent.
- **If the interview stage proves low-value on a real run**, the differentiation thesis weakens and the fixed fourteen-file taxonomy should be reconsidered before Phase 3 invests in per-file evidence.
- **If `claude/llms/` is scrapped**, Phase 0.1 shrinks to a deletion and roughly a week of future maintenance disappears with it.
- **If Hibernate 8.0 ships** and promotes `@SoftDelete`/`@View` out of `@Incubating`, or removes further deprecated annotations, bump the 1.1.3 vocabulary version and re-baseline. 8.0 is in development now (8.0.0.Beta1, 2026-06-16) and targets Jakarta Persistence 4.0.
- **If this repo moves into the Elsevier org**, `PORTING.md` is the checklist and the diff is one input. The one open question is whether the org accepts a plain runner label or requires the `group:` map form — resolve that against a real runner before assuming `fromJSON` templating works, since that path is undocumented. The coverage gate is also the structural slot a Sonar quality gate would occupy, so that swap is local to one step.
