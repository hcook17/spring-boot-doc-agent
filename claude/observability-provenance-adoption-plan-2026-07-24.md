---
category: Observability, provenance & data modeling — adoption plan
status: proposed; premise audit complete, no code written
source report: compass_artifact_wf-3ce824ed-b263-5f48-a180-f435227de2d1 ("Principals' Panel Review")
plan date: 2026-07-24
---

# Adoption plan for the observability/provenance panel review

## Context

An external research report recommends eight adoptions for this repo: DuckDB as a query
layer over append-only run records, structlog for logging, the in-toto/SLSA shape for
`run_manifest.json`, W3C PROV-O as a derivation vocabulary, Desbordante for empirical
schema discovery, reprotest+diffoscope to prove determinism, restructuring `derived_from[]`
as set-of-sets why-provenance, and rejecting OpenTelemetry/OpenLineage/lineage servers.

Direction given: adopt the recommendations, including the new dependencies.

This document is the plan for doing that. It leads with a premise audit because three of
the eight recommendations describe a repo state that does not exist, and adopting them
as literally written would produce work with no referent.

## Premise audit — read before executing anything below

The report is well-sourced on the outside world and wrong about the inside of this repo
in three specific ways. Each changes what "adopt" means for that recommendation.

**P1. The fact tuple does not exist.** The report analyzes
`{subject, predicate, object, qualifiers{}, citations[], confidence, derived_from[], layer}`
as a live schema whose weak fields must be measured before they "acquire a migration."
That tuple appears in exactly one place in this repo —
`claude/10-architecture-maturation-plan.md:144` — in a document whose frontmatter reads
`status: proposed; mostly not started`. No `.py` file, emitted JSON, or schema contains
`subject`, `predicate`, `derived_from`, `qualifiers`, or `layer`. What ships is a flat
evidence bag of `{file, line, match, rule_id}` plus the unary `entity_table_map`
(`spring_signal_scan.py:813-823`), which the plan at `:53` proposes to delete.

Consequence: the report's #1 "this week, highest leverage" item — profile
`qualifiers`/`confidence`/`layer` occupancy and delete them if under 5% — is unexecutable.
Occupancy is trivially zero because nothing has ever emitted them. The recommendation is
inverted: these fields have not survived long enough to become legacy, they have not been
built. Repointed in §D below.

**P2. There is no append-only run-record corpus.** `run_manifest.py:485-497` is
read-modify-write on a single file, one per run, in the orchestrator's working directory
(`CONSTRAINTS.md:22`). Nothing aggregates across runs. `CONSTRAINTS.md:62` states "No
multi-repo or batch story," and both `CONSTRAINTS.md:70` and `STATUS.md:34` rank
multi-repo support *last* in close-out order. DuckDB is proposed as a query layer over a
directory that does not exist and whose prerequisite is explicitly deferred. Sequenced in
§E.

**P3. The drift checker is already incremental.** The report lists "hand-rolled
incremental drift logic" as deletable in favor of DBSP's delta algebra.
`spring_drift_check.py` is a two-tier checker: whole-repo sha256 signature diff
(`:329-360`) gating a targeted per-changed-file ast-grep re-run (`:641-675`), with
multiset comparison and a post-loop provenance pass for JPQL citations whose freshness
depends on two files (`:518`). It has **eight** statuses (`:222-235`), not six.

The two extra statuses are why DBSP is a partial fit at best.
`suspected_drift_content_changed_no_rule_to_recheck` and `unknown_no_prior_signature` are
epistemic states — *I cannot determine whether this drifted* — and a delta algebra over
inserts and deletes has no representation for them. DBSP models what changed; the drift
checker also has to model what it is unable to observe. Take the "read DBSP before
hand-rolling" advice as overtaken by events, not as pending work.

Two smaller corrections worth carrying back to the report's author:

- **OpenLineage is already in use as a cited model**, not rejected wholesale.
  `spring_drift_check.py:187-194` borrows its run-lifecycle terminality rule
  (START/RUNNING non-terminal, only COMPLETE/FAIL/ABORT terminal) to decide when a
  manifest is trustworthy as a baseline. The repo's established practice is to read these
  specs and borrow vocabulary without taking the dependency — `analytics-logging:93` does
  the same with ML Metadata's status enum. "Reject" must be scoped to *as a service*.
- **OpenTelemetry appears in this repo only as something the tool detects in target
  repos** (`spring_ast_grep_rules.yml:222`, `doc-taxonomy.md:55`), never as something it
  uses. The report's rejection argument is sound but aimed at a decision nobody proposed.

**What the report gets right, and it is the most valuable thing in it:** the determinism
recommendation found a real latent defect by category. See §A1.

## Standing decisions this plan reverses

Both need an explicit written reversal, not a silent overwrite.

**R1. The no-new-dependencies rule.** `00-shared-research-standards.md:24` scopes every
artifact to "no new infrastructure or dependencies beyond what the plugin already assumes
(Python stdlib, `ast-grep` on PATH, no new services)." This has been enforced in writing
at least five times, including three separate refusals to add `jsonschema` — a pure-Python,
ubiquitous, near-zero-risk dependency (`run_manifest.schema.json:2`,
`test_run_manifest.py:54`, `citation_coverage.py:73`). That is the calibration bar being
argued against, and it is a high one.

New deps are not categorically banned — the maturation plan itself proposes six
(`sqlglot`, `jsonschema`, `hypothesis`, `syrupy`, `pydoclint`, PyYAML). The operative test
is the shape test at `10-plan:158`: "pure Python, no build step, no service." Measured
against it: **structlog passes cleanly. DuckDB fails "no build step"** (compiled wheel).
**Desbordante fails hardest** — compiled C++ core plus the license problem in R2.

**R2. Dependency license compatibility is an unwritten policy.** No document in this repo
addresses it. `CONSTRAINTS.md:59` covers only the plugin's own license field. This plan
would be the first thing to hit it.

The repo is MIT (`LICENSE:1-3`, `.claude-plugin/plugin.json`, `README.md:94`) and is
redistributed as a marketplace plugin. Desbordante's CLI artifact is AGPL-3.0. MIT and
AGPL are one-directionally compatible: combining them forces the *combined work* to
AGPL-3.0, which would silently relicense this plugin and invalidate four separate
statements of its license. AGPL §13's network clause is not triggered (nothing is served),
so the exposure is redistribution, not SaaS.

The repo already has the correct mitigation pattern in hand: `ast-grep` is invoked as a
separate process on PATH, never imported (`CONSTRAINTS.md:11`). Desbordante's primary
distribution is a Python module you `import`, which is the linking case AGPL is written to
catch. **This plan therefore adopts Desbordante only as an out-of-process, developer-only,
never-in-`requirements.txt` tool**, and writes that boundary down. Adopting it as an
import is not something to do without a deliberate decision to relicense.

## The plan

### A. Determinism — do this first, it is the only part with a proven defect

**A1. Fix the unsorted `entity_table_map` (correctness, standalone PR).**
`spring_signal_scan.py:760` populates `entity_table_map[class_name]` inside the ast-grep
match loop and emits it at `:816` without sorting. Every sibling structure in that file is
sorted for determinism — the evidence buckets are re-sorted at `:809-810` under a comment
stating that ast-grep's multithreaded match order is *not* stable across runs.
`entity_table_map` was missed, so `spring_signals.json` has run-to-run unstable key order
on identical input: same content, different bytes, unstable hash.

Already prescribed independently at `10-plan:117` and `:156`. One-line fix plus a test.
Keep this PR to fix + test only.

**A2. Add a determinism probe (stdlib, CI-wireable).** Run `scan()` twice over
`scripts/fixtures/spring_signals/` in one test and assert the serialized JSON is
byte-identical. This is what reprotest buys, at a fraction of the cost, inside the harness
that already exists. `10-plan:67` names this as the cheapest first step and states that
until it exists, "every claim about drift attribution here is unfounded."

> **Measured correction, 2026-07-24 (A1 landed).** The probe as described above **does not
> work** for the defect it was written for. Implemented as
> `test_two_scans_of_the_same_tree_serialize_identically`, it *passed* against the unfixed
> scanner, because two `scan()` calls inside one process observed the same ast-grep match
> order. What caught the bug was the explicit invariant `keys == sorted(keys)`, which is
> decidable on a single run.
>
> Generalize this before building more of §A: re-run-and-diff can only catch nondeterminism
> that varies under the conditions it happens to vary, and identical back-to-back
> invocations are the weakest such condition. Name the invariant where one exists. This
> also sharpens the case for A3 specifically — reprotest's value is *not* that it re-runs,
> it is that it re-runs under deliberately varied locale, timezone, umask, and filesystem
> order. That variation is the mechanism; a bare second run is not.

Also add `.gitattributes` with `* text=auto eol=lf` (`10-plan:123`) —
`compute_file_signature()` hashes raw bytes, so CRLF churn reports every file changed.

**A3. reprotest + diffoscope — adopt, but scoped to the deterministic stages only.**
The report treats the pipeline as reproducible. Four of its five stages are LLM calls, so
two runs over an unchanged repo produce different documentation *by construction*
(`10-plan:67`). Bit-identical is the wrong success criterion pipeline-wide, and
`10-plan:67` asks instead for "the variance as a number."

So: run reprotest's environment variation (locale, timezone, file ordering, umask) against
**Stage 0 only** — `spring_signal_scan.py`, `partition_repo.py`,
`build_cross_group_edges.py` — which is genuinely deterministic and is where A1's defect
lived. `diffoscope` on mismatch. Both are developer/CI tools invoked as processes, so
neither enters `requirements.txt`.

For the LLM stages, the right instrument is the repo's already-chosen one: `syrupy` golden
snapshots (`10-plan:125`, `:244`), which make model variance measurable and separable from
code drift. Do not point diffoscope at prose.

### B. Run manifest — add the missing provenance, keep the flat shape

The report's strongest new argument. `run_manifest.py` records inputs well
(`file_signatures`, `target_repo.commit_hash`, `dirty`) and records **no outputs and no
tool versions at all** — no Python version, no ast-grep version, no version of the plugin
itself. That is a real hole, and it is precisely the `subject[]` + `builder` half of the
SLSA predicate.

**B1.** Add `subject[]` — sha256 of each produced artifact: the fourteen docs,
`spring_signals.json`, `groups.json`, `drift_report.json`. Today outputs are only *counted*
(`evidence_tag_counts`), never hashed.

**B2.** Add `builder` — Python version, `ast-grep --version`, `sqllineage`/`pathspec`
versions if importable, plugin version from `.claude-plugin/plugin.json`, and the plugin's
own git commit. Degrade to `null` with a stderr warning, matching the existing git-failure
pattern at `run_manifest.py:168-185`.

**B3.** Add `metadata.reproducible` — but only as an assertion A2 actually proves, and
only over the deterministic stages. An unearned `reproducible: true` is worse than the
field's absence.

**Do not adopt the materials/products/environment indirection.**
`analytics-logging-research-2026-07-24.md:95` already considered and declined it as "a
layer of indirection this five-stage, single-repo pipeline doesn't need," and that
reasoning still holds. B1–B3 are *added fields*, not a restructure — bump
`run_manifest.schema.json` `schema_version` 1 → 2 and extend
`test_run_manifest.py`'s `validate_manifest_shape()`.

The report should be read as supplying a rationale the 2026-07-24 pass did not consider
(`metadata.reproducible` as a mechanically provable claim), not as discovering in-toto
first. That pass evaluated in-toto directly (`:34`, `:44`). SLSA specifically is new.

### C. Provenance algebra — design-only, and the highest leverage per hour

Because of P1, this is not a refactor. `derived_from[]` is a sentence in a markdown file,
which makes now the cheapest moment in the project's life to get its algebra right.
`10-plan:149` states the cost of getting the record shape wrong: it is a cross-version
contract, and "promoting a qualifier into the key later is a breaking change that
invalidates every stored baseline."

**C1. Audit the derived rules before choosing the shape.** The plan's derived facts at
`10-plan:177` — `SINGLE_TABLE` suppression, `mappedBy` owning-side resolution,
`@FilterDef`→`@Filter` — all *look* conjunctive (a fact needs all its inputs). Set-of-sets
why-provenance buys the ability to express *alternative sufficient witnesses*. If no rule
produces one, the outer nesting is unused generality and a flat list plus a rule-id is
honest. Check this first; it is a half-hour of reading and it decides C2.

**C2. If any rule admits alternative derivations, specify `derived_from[]` as set-of-sets**
at `10-plan:144` and `:178`: inner set = one complete derivation (AND of its members),
outer set = alternatives (OR). Record the laws it must satisfy — `×` distributes over `+`,
both associative and commutative, `0` = no derivation, `1` = base fact — citing
Green–Karvounarakis–Tannen (PODS 2007). The payoff the report names is real and is exactly
the drift checker's job: "is this fact still supported if input X drifts?" is answerable
against an AND/OR structure and not against a flat list.

**C3. Note the alignment with what already ships.** `spring_drift_check.py:105-140` already
implements per-citation provenance *sets* — "a citation is fresh iff every file in its
provenance is unchanged," with JPQL's provenance being
`{own file, entity_table_map[entity]['file']}` — and `:138-140` states that a second
derived-citation type "only needs to name its own provenance set the same way." That is
one inner set. The report's set-of-sets is its natural generalization, which is a point in
its favor: the two layers would share a model rather than diverge.

**C4. PROV-O as annotation, not structure.** `10-plan:144` already commits the tuple's
shape to SCIP's `Relationship` plus Datomic's provenance dimension, with EDB/IDB
terminology from Datalog (`:176`). PROV-O would be a competing vocabulary on top of an
already-chosen structure. Adopt it as a documented mapping — fact = `prov:Entity`, scan run
= `prov:Activity`, `derived_from[]` = `prov:wasDerivedFrom`, `qualifiers` =
`prov:qualifiedDerivation` — so the model is legible to outsiders, without restructuring
anything to match it.

### D. Empirical profiling — repointed at data that exists

Per P1, the fields the report names cannot be profiled. Repoint at the fields that ship,
which raises genuine open questions:

- Does `rule_id` functionally determine its evidence bucket?
- Does `class_name → table` actually hold as a key, or do collisions occur under
  `inferred-default-naming` (`spring_signal_scan.py:588`)?
- What is real occupancy for the optional entry fields — `query_kind`, `lineage`,
  `repository`/`entity`/`id_type`, `class_name`?
- How often is `lineage.available` false, and for which `query_kind`?

The last one is directly decision-relevant and nothing currently measures it.

**Method.** DuckDB's `read_json_auto` plus `COUNT(*)`/`COUNT(field)`/`approx_count_distinct`
answers occupancy and cardinality with no second tool. Desbordante adds FD/UCC/IND
discovery on top. Run Desbordante **out-of-process via its CLI, from a developer machine,
never imported and never in `requirements.txt`** (R2), and record that boundary in
`CONSTRAINTS.md` as the repo's first written dependency-license policy.

Name the epistemological tension rather than letting it sit: `02-pluggability:30` and
`10-plan:148`/`:158`/`:159` commit this repo to *declaring* schemas and reconciling against
authoritative artifacts, not *inferring* them from instances. Profiling is legitimate as a
tool for deciding what to declare. It should not become the source of truth for the
contract.

### E. DuckDB and structlog — adopt, with the prerequisite stated

**E1. DuckDB.** Per P2 there is no corpus to query. To make this useful rather than
ceremonial, `run_manifest.py` needs to also append a record to a `runs/` directory keyed by
`run_id` — a small change, and the thing that turns "one manifest per run, discarded"
into a queryable history. Until that exists and has accumulated more than a handful of
runs, DuckDB is a SQL engine over a single file.

Sequence it that way: append-to-`runs/` first, DuckDB when the corpus justifies it. Note
that `10-plan:265` treats adopting a query engine as a *threshold* decision requiring an
explicit constraint relaxation, not an incremental add.

**E2. structlog.** Greenfield — there is no `import logging` anywhere in `scripts/`, and
every diagnostic is a bare `print()` (17 in `run_manifest.py`, 11 in
`spring_drift_check.py`). So this is not a migration off a bad logging layer; it is a
decision to have one. The concrete payoff is threading `run_id` through diagnostics, which
today happens nowhere outside `run_manifest.py:481` — that is what makes a multi-stage run
debuggable after the fact.

structlog passes the `10-plan:158` shape test cleanly. Adopt with `~=` per
`08-dependency-pinning:19`, and preserve the existing stderr-warning/stdout-summary
convention rather than reformatting every message.

### F. Governance — required, not optional

- **Amend `00-shared-research-standards.md:24`** to state the new dependency posture and
  the shape test that replaces the blanket rule. Per `CLAUDE.md`, `00`–`06` are mirrored
  from the attached Claude project and this edit **must be mirrored back**.
- **Add a dependency license-compatibility policy to `CONSTRAINTS.md`** (R2) — the
  out-of-process rule for copyleft tooling, with `ast-grep` as the existing precedent.
- **Append one `claude/session-log.md` entry** covering the prompt-assumption impact of
  whatever lands.

## Sequencing objection, stated plainly

`10-plan:261` is the repo's own stated highest-priority action: "**Run the current pipeline
end-to-end against one real service.** You are about to spend three weeks re-shaping the
core data structure on fixture-derived evidence." `MATURITY_ASSESSMENT.md:14`, `:16`, `:18`
and `STATUS.md:20` independently confirm that `capacity_preflight.py`, `run_manifest.py`,
and `semantic-pipeline-eval` have only ever run against
`scripts/fixtures/spring_signals/`.

Every item in this plan is infrastructure layered on a system its own docs say has never
been exercised on a real repository. That objection applies to the report as a whole,
independent of any single recommendation's merit — and it applies with particular force to
§D, whose entire value proposition is *measuring real data* that does not yet exist. A
single real-repo run would make §D meaningful and would sharpen §A2 and §B1.

§A1 is the exception and should proceed regardless: it is a defect, it has a one-line fix,
and it does not depend on anything above.

## Verification

- **A1** — `python3 scripts/test_spring_signal_scan.py -v`; new test asserts
  `entity_table_map` key order is sorted, and that two `scan()` calls serialize identically.
- **A2** — same suite; probe test must fail before A1 lands and pass after. Wire as a CI
  step alongside the existing thirteen.
- **A3** — `reprotest` over Stage 0 against the fixture tree; `sha256sum` compare;
  `diffoscope` only on mismatch. Local/CI only, no `requirements.txt` change.
- **B** — `python3 scripts/test_run_manifest.py -v`; extend `validate_manifest_shape()`
  for `subject[]`, `builder`, `metadata.reproducible`; CLI round-trip must still pass.
- **C** — no code; the deliverable is the edited `10-architecture-maturation-plan.md`
  sections plus the C1 audit result written down.
- **D** — a written findings note in `claude/`, dated, with the profiling queries included
  so the result is reproducible.
- **E** — `python3 scripts/test_run_manifest.py -v` for the `runs/` append; full suite
  (307 passing on `main` as of the last session-log entry) must stay green.
