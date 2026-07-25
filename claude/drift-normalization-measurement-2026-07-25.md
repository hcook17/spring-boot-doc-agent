# How often does `spring_drift_check` tier 2 cry wolf, and would Rust help?

**Date:** 2026-07-25
**Question asked:** is a Rust/tree-sitter AST fingerprint worth adding to `spring_drift_check`, where
the subjects genuinely are Java files?
**Answer:** no — measured. The ceiling on what any better fingerprint could buy is **2 wrong verdicts
in 208**, and a ~30-line stdlib tokenizer already reaches it. A separate, narrower Rust case did
surface, in the test harness rather than the tool; it is stated at the end and not acted on.

Everything below is re-derivable by `python3 scripts/test_drift_normalization.py`.

---

## Why this was measured rather than argued

The prior session scoped a Rust `astsig` binary for `_ast_signature.py`, then withdrew it on
measuring that **0 of 22** predicate subjects were `.java` — that module fingerprints claims *this
repo* makes about itself, and this repo is Python and markdown. The remark that closed it was that
the honest home for Rust would be `spring_drift_check`, whose subjects really are Java, *if* the
marginal gain over ast-grep tier 2 could be shown.

This is that measurement. It is deliberately the same discipline that overturned the `t1` default in
`_ast_signature.py`: state the relation, build a corpus where the correct answer is known in advance,
and count.

## Method

Two arms, because one is not enough:

- **False positives.** Perturb the Java fixtures in ways that provably preserve the parse tree —
  Type-1 clones in Zhang & Saber's taxonomy (arXiv:2506.14470 §II-A): comments, indentation, blank
  lines, and annotation arguments wrapped across lines. Every `drifted` verdict is wrong by
  construction, with no judgement call in scoring it.
- **Missed real changes.** Semantic edits chosen to keep the citation *count* identical while
  changing citation *content*: a mapping path, an HTTP verb, an `@Table` name. Every `confirmed`
  verdict on one of those is wrong.

The second arm is not optional. The first is trivially winnable by an identity function that returns
`""` for every input: perfect on false positives, blind to everything. No result below is quoted
without its partner.

## The instrument was wrong first, and that is the most transferable finding

The first run reported **7 false positives in 208, across five rules**. That number was an artifact.
The perturbation rewrote annotation-looking text *inside comments*, broke a doc comment's closing
quote, and left the files unparseable — so ast-grep returned nothing and every citation in them read
as drift. It was measuring the harness. Caught only by opening the files by hand.

The corrected figure is **2 in 208, in one rule**. A 3.5x overstatement, in the direction that would
have justified the work being evaluated.

So the harness now carries a validity gate — a formatting-only edit must leave the same number of
citations discoverable by a fresh scan — and the broken perturbation is **kept as a test input**
(`java_perturbations.broken_wrap_annotation_args`), with `Test00HarnessValidityGate` asserting the
gate rejects it. A gate that has never been shown to reject anything is not a gate; this one has a
specific thing it is known to catch, because it failed to catch it once.

## Result

| identity relation | false positives | missed real changes |
|---|---|---|
| `first_line` — **status quo** | **2 / 208** | 0 / 2 |
| `collapse_ws` | 2 / 208 | 0 / 2 |
| `strip_ws_outside_strings` | **0 / 208** | 0 / 2 |
| `tokens` | **0 / 208** | 0 / 2 |

Per perturbation, against the status quo: `add_comment` 0, `reindent` 0, `blank_lines` 0,
`wrap_annotation_args` **2**. This is one specific class of edit, not general brittleness.

### The cause is not a missing parser

ast-grep hands back the **whole** match. `spring_signal_scan._first_line_match()` keeps
`text.splitlines()[0]`:

```
ast-grep returns : '@RequestMapping(\r\n        "/api/invoices"\r\n)'
stored identity  : '@RequestMapping('        <- compares equal to nothing
```

The structural information is already in hand on the Python side and is being discarded. That is why
no parser — in Rust or anywhere else — can beat a tokenizer here: both start from the same string,
and the string is already correct.

`collapse_ws` is in the table as a recorded negative result. It is the obvious first fix, and it does
not work: `@Get( "/x" )` still differs from `@Get("/x")`. Pinned by a test so it is not re-proposed.

`tokens` is preferred over `strip_ws_outside_strings` at equal measured cost because it is
**injective** and the other is not: `strip_ws_outside_strings("int a") == strip_ws_outside_strings("inta")`.
Whether that collision is reachable from ast-grep match text is unknown, and an unproven collision is
still a collision. Both properties are asserted in `Test05NormalizerProperties`.

## Why the fix is not in this change

`_first_line_match()` does two jobs. It decides what tier 2 **compares**, and it decides what
`spring_signals.json` **stores** as each citation's `match` field — human-readable evidence that a
`doc-writer` agent reads. A token sequence joined by `\x1f` is an excellent identity and unreadable
evidence. Splitting those two jobs changes the stored schema, so it is its own decision, and it
should be made against the table above rather than against an intuition about which looks tidier.

Recorded as `CONSTRAINTS.md` "Known precision tradeoffs" item 9, flagged and not resolved.

## The Rust question, answered

**Not for the fingerprint.** The ceiling is 2/208 and Python stdlib already reaches it. Adding a
compiled binary to collect a gain that is already collected would be indulgence, and it would put a
required Rust toolchain in front of a plugin that ships as a git checkout with 0 releases and 0 tags.

**There is one real case, and it is in the harness, not the tool.** The validity gate above is a
*proxy*: it asserts the citation count is unchanged, which caught the actual defect but could pass
while a file is still broken in a way that does not move a count. A direct oracle would assert the
perturbed file's AST equals the original's modulo whitespace and comments. That needs a Java parser:

- Python's stdlib has none.
- **ast-grep cannot stand in, verified on 0.44.1.** `--strictness relaxed` is exactly the right
  relation ("ast nodes except comments"), but a whole file cannot be used as a pattern —
  `Error: Multiple AST nodes are detected`. `--debug-query` dumps the *query*'s tree, never a file's.
  There is no tree-dump subcommand, and `ast-grep outline` is far too thin (a 26-line Java fixture
  with entities and annotations yields one line).

Such a tool would sit in the **test lane only**, so `00`'s "Python stdlib, `ast-grep` on PATH, no new
services" runtime constraint would stand unamended — it never enters the shipped path. Paired with
`proptest`, it would also replace the four hand-written perturbations here with generated ones, which
matters: **the 2/208 figure is bounded by what one person thought to try, not by the checker.**

That is a real proposal and it is not made here. It should be justified by its own measurement — how
many additional false positives a generated corpus finds over these four transforms — in the same way
this document declined to justify the first one.

## Hazards left uncovered, stated rather than omitted

- Corpus is 9 Java files, 4 perturbations. **2/208 is a floor, not a bound.**
- Only Java is perturbed. YAML, SQL and `.properties` citations ride the same generic comparison and
  are never exercised for formatting sensitivity.
- No encoding or line-ending perturbation. A CRLF/LF flip *would* be seen by tier 1, which hashes raw
  bytes; untested here because the harness reads and writes UTF-8 text throughout.
- `wrap_annotation_args`' `or "//" in line` guard is not exercised — an injection removing it was
  expected to trip the validity gate and did not, because line-scoping alone suffices on this corpus.
  Kept as defence in depth, but nothing demonstrates it is load-bearing.
