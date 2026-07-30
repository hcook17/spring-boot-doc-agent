---
name: citation-coverage
description: Prevent and detect missing, dropped, and mis-anchored evidence citations in document-spring-repo output — the failure class where a claim carries no tag at all, or carries an [Evidenced — path:line] tag whose line does not actually support it. Read the authoring rules BEFORE writing or reviewing any of the fourteen docs (they are what actually reduces the defect rate); run python -m doc_engine.tools.citation_coverage after a run to catch what slipped through. Distinct from check_pipeline_output.py (gates tag shape and citation resolvability, but is structurally blind to an absent tag) and semantic-pipeline-eval (judges whether claims that already carry a tag are true). Use whenever citations are being missed, dropped between stages, or invented to satisfy the tag grammar.
---

# Citation coverage

## The blind spot this closes

This pipeline has two citation checkers, and **neither can see a citation that
isn't there**:

| Mechanism | What it checks | Why it can't see an omission |
|---|---|---|
| `check_pipeline_output.py` → `doc_tag_utils.py` | tag shape, citation resolvability | `find_malformed_tags()` only matches bracket spans **already starting with a tag word**; `resolve_evidenced_citations()` only iterates `[Evidenced]` **matches**. An untagged sentence matches neither, so it isn't "failing" — it's invisible. |
| `skills/semantic-pipeline-eval/` | whether a tagged claim is *true* | It **samples `[Evidenced]` claims** — claims that already carry a tag. |

So the entire verification stack is keyed on tags that exist. An omitted
citation is the one defect none of it reports — which is exactly the defect
that keeps getting reported by hand.

Three further holes make this worse than it looks:

- `check_tags_and_citations(docs_dir, None)` returns `[]`. There is a test
  asserting it (`test_citations_skipped_without_target_repo`). **Forget
  `--target-repo` and the gate passes having checked no citations at all.**
- `resolve_evidenced_citations()` proves only that the path exists and that
  the file has at least that many lines. `Foo.java:3` for a fact at line 87
  resolves clean.
- Untagged bullets were **knowingly** left unflagged in an earlier validator
  ("a bullet with no tag at all not flagged" — an accepted regression at the
  time, for a different artifact). That decision is why this gap is old.

## Why citations go missing — the actual mechanisms

Not carelessness. Four structural causes, each with its own countermeasure:

**1. Line numbers are destroyed mid-pipeline.** `spring_signal_scan.py` emits a
`line` per hit. The file-summarizer's output schema (`agents/file-summarizer.md`)
does **not** — it carries `"file": "relative/path.java"` and prose, no line
field. So every business-logic fact reaching `doc-writer` through
`summaries.json` is path-only. A writer asked for `path:line` that has only
`path` will do one of three things, and two of them are defects: omit the tag,
degrade to a file-only citation, or **invent a plausible line number**.

**2. The evidence slice can arrive empty, silently.** A path-separator
mismatch between `groups.json` and `spring_signals.json` once left Stage 1's
evidence slice empty for *every* dispatch — 54 of 55 files unmatched — with
"no error, no warning, no empty-output signal." Subagents fall back on reading
files themselves and the run completes, producing plausible documentation built
on nothing. Any stage that silently degrades to zero evidence produces
uncitable prose by construction.

**3. Citations get reconstructed from memory at write time.** The observed
shape: a fact genuinely present at lines `:201`, `:214`, `:223` was cited as
`:272`. Also observed: a module docstring citing
`_query_citations_depending_on_entity()` and `_flag_stale_jpql_lineage()` —
"neither name has existed at any commit," reading "like names from a design
sketch." A citation written from recollection of a file is a guess wearing a
tag's clothes.

**4. Silence is cheaper than `[Unknown]`.** Every tag form is auditable; no tag
is not. Under any pressure — a fact that resists evidencing, a long document, a
crowded context — omitting the sentence's tag is the locally easiest move and
the one with no downstream consequence. That asymmetry is the root incentive
problem, and rule A5 below is the direct counter.

## A. Authoring rules — read these before writing or reviewing any doc

These are what actually reduce the defect rate. The script below only catches
what escapes them.

**A1. Capture the citation at read time, never at write time.** The moment you
read a fact out of a file, record `path:line` with it. Do not plan to "add
citations at the end" — by then the line number is a recollection, and cause 3
above is what recollection produces.

**A2. Take line numbers only from a source that actually carries one.** There
are three: `spring_signals.json`'s per-hit `line`, `summaries.json`'s per-file
**`evidence`** array (`{"line": N, "what": "..."}`), and a file you opened
yourself. A summary's *prose* — its `summary` and `group_function` text — carries
no line, so anything line-shaped derived from prose alone is invented. If a claim
has no anchor in any of the three, **re-open the file and find the line**. You
have `Read`, and `ast-grep` via `Bash` for structural search — use them. Not text search: it matches inside strings and comments, which mis-anchors the very citation you are trying to fix. Try both `@Name` and `@Name($$$)`, and treat a zero result as unproven rather than absent.

**A3. A file-only citation is legitimate; an invented line is not.** If you
genuinely cannot localize a claim to a line, `[Evidenced — path/File.java]` is
one of the taxonomy's five valid forms. Reach for it rather than guessing a
number to make the citation look precise. Precision you didn't earn is worse
than admitted imprecision.

**A4. Don't cite a file you didn't open.** Signal-scan hits are ground truth
for *what* is at a location, and citing them directly is fine. Anything beyond
what the scan literally recorded requires you to have read the file.

**A5. When you can't evidence it, tag `[Unknown]` — do not go quiet.** The
required form is
`[Unknown — not evidenced in code, not covered in interview]`. An unevidenced
claim with a tag is a visible, auditable gap. The same claim with no tag is
indistinguishable from a verified one, and nothing downstream will ever surface
it. If a claim can't earn any of the five tags, delete the claim.

**A6. Check your evidence slice is non-empty before you start.** If your
dispatch handed you a signals slice or a `cross_group_edges` entry that is
empty, say so in your confirmation line rather than quietly proceeding on your
own reads. An empty slice is cause 2, and it has no other alarm.

**A7. "I can't see X here" is a finding; "X doesn't exist" is an inference.**
When something isn't reachable from your context, report the limit of your view
rather than upgrading it into a claim about the repo.

**A8. `[Evidenced]` means directly readable — not "strongly supported."** These
tag names carry two different meanings in this repo, which is a live hazard
rather than a hypothetical one. The review layer
(`claude/steering-prompts/10-review-persona-and-standards.md` and sessions using
it) defines `[Evidenced]` as *"strongly supported, one inference step short of
executed proof"* and `[Confirmed]` as *"traced in source + verified against the
tests."* `doc-taxonomy.md` means something stricter and different: `[Evidenced]`
is a fact you can read at the cited location, and `[Confirmed]` means a human
said so in the interview, nothing else. Carrying the review-layer definitions
into doc-writing silently converts inferences into evidence. When writing any of
the fourteen docs, `doc-taxonomy.md`'s definitions are the only ones in force.

If a claim is one inference step past what the cited line literally shows, the
taxonomy already has the honest form for it:
`[Evidenced — path/File.java:42; inference avoided beyond this]`. Use it instead
of stretching `[Evidenced]`.

Worth naming the mechanism, because it generalizes: a research subagent in this
project's history correctly self-reported sources it had found but never opened
as `PLAUSIBLE-BUT-UNVERIFIED` — and did so *only because its prompt forced a
two-tier tag*. Plain `[Evidenced]` has no such forcing function. The five tag
forms only work if the writer treats "which tier is this actually?" as a
question to answer, not a formality to satisfy.

## B. Detection pass

After a live generative run, prefer the orchestrator gate suite (includes citation coverage when configured):

```bash
doc-engine pipeline gates --out-dir <run_dir> --target-repo <repo_path> --docs-dir docs/
```

Or, after `pip install` of doc-engine:

```bash
python -m doc_engine.tools.citation_coverage docs/ --target-repo <repo_path>
```

**Do not** invoke deterministic tools via the plugin install tree (no `scripts/` under the marketplace plugin root).

Two checks, both **worklists, not verdicts** — same framing
`semantic_eval_helpers.find_unmatched_confirmed_tags()` uses:

- **`untagged_claim`** — a sentence naming a concrete repo artifact (source
  path, `@Annotation`, CamelCase type, `method()`, dotted config key,
  `SCREAMING_SNAKE` constant) that carries no tag of any kind. The
  artifact gate is deliberate: flagging every untagged sentence buries real
  findings under narration, so the rule is the narrowest one that still works —
  *if you named a code artifact, cite where it lives.* Prose, headings, fenced
  code and mermaid blocks, table rules, and the taxonomy's own placeholders
  (`None found`, `asked, not answered`) are exempt.

- **`miscased_tag`** — a bracketed span that reads as a tag in some casing
  other than the required one (`[evidenced — Foo.java:6]`). Every pattern in
  `doc_tag_utils.py` is case-sensitive, so such a span is **neither a valid tag
  nor a malformed one** — it matches `TAG_PATTERNS` not at all and
  `TAG_WORD_SPAN` not at all, so `find_malformed_tags()` never sees it and the
  tag counters score it as absent. A prior session named it exactly: *"a fully
  different casing isn't caught as malformed, it's simply invisible to a
  grep-shaped check."* It is a citation the writer genuinely made and every
  counter in the repo reports as missing, which is why it gets its own finding
  rather than being folded into `untagged_claim`.

- **`symbol_absent_from_file`** / **`symbol_outside_window`** — a
  `[Evidenced — path:line]` whose claim names symbols that appear, respectively,
  nowhere in the cited file (the stronger signal — the shape of a citation
  invented to satisfy the grammar) or in the file but not near the cited line
  (a real file, an imprecise anchor). The split matters: they have different
  causes and different fixes.

Both are heuristics, so the script exits 0 by default — pass `--strict` to make
findings fail a build. It does **not** judge whether a well-anchored claim is
true; that boundary belongs to `semantic-pipeline-eval`, same line
`check_pipeline_output.py` draws around itself.

**Run it with `--target-repo`.** Without it the anchor check cannot run — the
script says so in its output rather than returning clean and silent, which is
the trap `check_tags_and_citations` sets.

## C. Where this sits in a run

Order matters — each stage narrows what the next has to look at:

1. `check_pipeline_output.py` — the gate. Shape, resolvability, file set,
   write scope. **Blocking.**
2. `citation_coverage.py` — this skill. Omissions and bad anchors.
   Advisory by default.
3. `skills/semantic-pipeline-eval/` — truthfulness of what remains.
   Advisory, model-driven.

A doc can pass 1 cleanly while every substantive claim in it is uncited, which
is the whole reason 2 exists.

## What this deliberately does not catch

- **A file-only citation on a claim that needed a line.** `TAG_PATTERNS`'
  `(?::(\d+))?` makes the line number optional, so `[Evidenced — Foo.java]` is
  structurally valid for any claim at all. Flagging it whenever the claim names
  a symbol would fire on every legitimate whole-file citation, and the taxonomy
  explicitly blesses that form. There is no mechanical way to tell "whole-file
  claim" from "specific claim, line omitted" — rule **A3** is the only control.
- **Vendored or generated code cited as first-party.** A `[Evidenced]` tag
  pointing into `vendor/` resolves, and its symbols are genuinely there, so both
  checks pass. That is a scanner-scope concern (`EXCLUDED_DIRS`), not a coverage
  one.
- **Whether a well-anchored claim is true.** `semantic-pipeline-eval`'s job.

## The upstream fix that made this tractable

The detection layer above cannot, on its own, fix a line number that was never
passed downstream. A static trace of all six stages found the real mechanism:

| Stage | Artifact | Carries a line? |
|---|---|---|
| 0 `spring_signal_scan.py` | `spring_signals.json` | **yes** |
| 1 `file-summarizer` | `summaries.json` | **no — dropped here** |
| 2–3 architect | Mermaid | no, by design |
| 4 `gap-analyzer` | `gap_questions.json` | **no** |
| 5 `doc-writer` | `docs/*.md` | **required** |

Line-precise evidence existed only at Stage 0, was required only at Stage 5, and
every carrier between them was line-free *by schema*. So `doc-writer` could
line-cite only what Stage 0's ast-grep rules mechanically matched; every claim
from the semantic layer — the bulk of the fourteen docs — arrived with a path
and no line. **That is an information gap, not a prompt-compliance gap**, which
is why the authoring rules above can reduce it but never close it: no
instruction can restore a line number that was never passed.

Closed by adding an `evidence` array (`{"line": N, "what": "..."}`) to the
file-summarizer's per-file output — Stage 1 is the only stage holding both the
open file and the semantic claim, so it is the one place the anchor is
recoverable at near-zero marginal cost. Enforced in
`scripts/test_pipeline_stages.py`'s `required_keys`, so it is a contract rather
than a suggestion. `gap-analyzer`'s `evidence` field got the same treatment for
the `[Confirmed]` lane, which had no provenance discipline at all — its own
canonical example shipped an unresolvable elided path.

**This prediction is falsifiable with tooling already in the repo.** If the
diagnosis is right, `run_manifest.py`'s `compute_evidence_tag_counts()` should
show the line-cited fraction rise, and this skill's `symbol_outside_window` rate
should fall. If both stay flat across a re-run, the root cause is elsewhere and
the schema change should be reverted rather than defended.
