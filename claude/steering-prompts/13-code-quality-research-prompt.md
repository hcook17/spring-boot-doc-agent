---
category: Code quality / expressiveness — naming, function size, information hiding, domain language
status: partially resolved (2026-07-24) — the mechanical layer landed (`ruff` + `scripts/check_code_quality.py`'s committed per-function baseline, both CI-wired and blocking), and the two live defects the measurement pass surfaced are fixed. The expressiveness work itself — one stage vocabulary, single-owner tag grammar, a glossary, typed cross-stage artifacts — is scoped below and NOT done. See `claude/session-log.md`'s two 2026-07-24 entries.
authored: in this repo, not mirrored from the Claude project — no sync obligation (see `00-shared-research-standards.md`'s `07`–`12` rule)
---

# Research + scaffold prompt: code quality and expressiveness

Read `claude/steering-prompts/00-shared-research-standards.md` first for the evidence bar, and
`10-review-persona-and-standards.md` for the tier vocabulary. This prompt was written after the
work in its first phase had already been done, so unusually it states measurements rather than
predicting them — treat the numbers as of 2026-07-24 and re-measure rather than trusting them.

## The gap

Every other quality property in this repo is enforced by something that runs: evidence tags by
`check_pipeline_output.py`, citations by `citation_coverage.py`, PR docs by
`check_llms_coverage.py`, scan freshness by `spring_drift_check.py`. The code itself was enforced
by nothing — no linter, no formatter, no complexity bound, no import ordering — and the CI workflow
ran thirteen test suites and zero style checks.

That mattered less than it usually does, because the conventions here are unusually good and were
being held by hand: test names are behavioural to the point of being sentences, duplication is
mostly deliberate and annotated in place with its reason, and three modules are fully type-annotated.
The problem is the *unenforced* part. Measured on 2026-07-24:

- 21 of 149 production functions carried any type annotation (14%), and the distribution is the
  finding: it is all-or-nothing per module. `build_cross_group_edges.py` 6/6,
  `check_llms_coverage.py` 7/7, `check_pipeline_output.py` 8/8 — every other module at zero. The
  convention exists and was simply never applied backwards.
- 25 functions exceeded cyclomatic complexity 10. The worst was `partition_repo.build_groups()` —
  which is exactly where `10-review-persona-and-standards.md` §1 records the `carry_forward`
  termination bug, and where the kitchen-sink suite then found a *second* infinite loop in the same
  guard. Complexity concentrates where defects land, in this repo's own history.
- Zero `dataclass`/`NamedTuple`/`TypedDict` anywhere, while the four JSON artifacts that flow
  between pipeline stages are passed as bare dicts and read with chains like
  `signals["evidence"]["raw_queries"]`.

## Research

The reading this was drawn from, and how it actually mapped — most of it did not, and saying so is
the point:

- **A Philosophy of Software Design** (Ousterhout) — *information leakage* is the real problem here
  and the one that keeps producing bugs. Live examples: `TAG_PATTERNS["evidenced"]` uses unnamed
  groups and two callers hardcode `m.group(1)`/`m.group(2)`; `load_gitignore_spec()` returns `None`
  for two different conditions; `run_manifest.py` maintains `_TAG_KEY_MAP` purely to re-case another
  module's dict keys.
- **Domain-Driven Design** (Evans) — *ubiquitous language*. See the scope below; this is the largest
  remaining piece.
- **Refactoring** (Fowler) — supplies the named, test-guarded moves (Extract Function, Replace
  Primitive with Object, Introduce Parameter Object). Method, not target.
- **Fluent Python** — the Python-specific expression: `dataclass`, `NamedTuple`, `Enum`, `typing`.
- **Clean Code** — function size is real and now ratcheted; the naming advice is largely already
  satisfied here, which is worth stating so nobody "fixes" it.
- **Patterns of Enterprise Application Architecture** — catalogues patterns for layered, DB-backed
  enterprise applications. This is a CLI toolchain over JSON artifacts. **Weak fit; skip it.**
- **The Clean Coder** — about professional habits, not code. `CONTRIBUTING.md`, `STATUS.md`,
  `session-log.md` and the evidence-tier discipline already exceed what it prescribes.

Tool research, per `00`'s star/recency methodology, verified against the GitHub API on 2026-07-24
rather than a blog: `ruff` 48,828 stars, latest release 0.16.0 published 2026-07-23, pushed
2026-07-25 — active, and one binary replacing flake8 + black + isort. `radon` (1,997 stars) was
rejected: last push 2024-10-20, ~21 months stale, at `00`'s "legacy snapshot" line.

arXiv, Tier A, verified at `arxiv.org/abs/2007.12520`: *An Empirical Validation of Cognitive
Complexity as a Measure of Source Code Understandability* (Muñoz Barón, Wyrich, Wagner, 2020),
~24,000 understandability evaluations over 427 snippets, meta-analysed. Cognitive Complexity
correlates positively with comprehension *time* and with subjective ratings; results are **mixed**
for correctness and physiological measures, and the paper does **not** compare against other
metrics. State that honestly — it supports "keep complexity low," not "this metric is validated
against McCabe."

## What was scaffolded (phase 1, done)

`scripts/check_code_quality.py` — stdlib `ast`, in the idiom of this repo's six existing checkers.
Records per-function statement count / cyclomatic complexity / nesting depth plus production-module
annotation coverage into a committed `scripts/code_quality_baseline.json`, and fails only on
*regression*. A fixed threshold was rejected on the usual grounds: on an existing codebase it is set
either above everything (enforces nothing) or below something (fails on day one, gets disabled).

Two design notes worth preserving, both learned by the gate firing on its own author:

1. **Statements, not line span.** The first draft measured `end_lineno - lineno` and immediately
   flagged a function that had grown only by an explanatory comment. This repo is deliberately
   38–54% prose in its larger modules; a metric that reads *documenting something* as *making it
   worse* is one that gets deleted.
2. **Annotation coverage counts production modules only.** Test methods are never annotated, so
   including them means adding a suite lowers the ratio and fails the build. A check that penalizes
   writing tests will not survive.

## What is still open

1. **One stage vocabulary.** Four competing naming schemes for the same five stages
   (`run_pipeline_local.py`'s `STAGE_*`, `capacity_preflight.py`'s `stage1_*` fan-out keys, the
   hyphenated subagent names, and two rival stage-*numbering* schemes), reconciled by a
   hand-maintained `PREFLIGHT_TO_MANIFEST_STAGE` dict whose own comment concedes the vocabulary
   "independently evolved". **Read the change surface before touching this**: neither vocabulary is
   validated on write, `run_manifest.schema.json` types `stages[].name` as a bare string with no
   enum, and the one production join (`run_manifest.py`'s predicted-vs-actual fan-out) fails *open*
   — so a half-completed rename yields silently wrong telemetry with green tests. Prefer a shared
   constants module plus validation over a rename; `_shared_excludes.py` is this repo's own
   precedent for fixing an already-drifted vocabulary by extraction.
2. **Single-owner tag grammar.** The `[Confirmed]` regex has two independent owners
   (`doc_tag_utils.py` and `semantic_eval_helpers.py`) that have already diverged, in the module
   whose docstring says it exists to prevent exactly that.
3. **A glossary.** `agents/gap-analyzer.md` instructs the pipeline to treat "an entity/domain term
   used inconsistently across modules" as an interview-worthy defect in the *target* repo, and
   `doc-taxonomy.md` says "if the same word means different things in different modules … ask rather
   than invent." This plugin has no glossary of its own terms. `evidence` and `artifact` carry six
   senses each; for `evidence`, three of them are the same JSON key with incompatible types.
4. **Typed cross-stage artifacts** — the in-code half of
   `02-pluggability-research-prompt.md`. Coordinate with it rather than inventing a second
   representation: the typed structure *is* the schema.
5. **`ruff format`** — not adopted. 29 of 33 files would be reformatted; that belongs in its own
   commit with a `.git-blame-ignore-revs` entry, not riding along with a semantic change.
