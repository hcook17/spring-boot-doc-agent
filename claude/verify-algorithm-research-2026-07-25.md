# The verify algorithm — research, 2026-07-25

Researched to `claude/steering-prompts/00-shared-research-standards.md` (arXiv confirmed to resolve
*and* to say what is claimed of it; GitHub filtered on stars **and** push recency; every claim tagged
verified-from-a-source-I-opened versus not), with `10`'s Tier A/B/C vocabulary.

**Question:** what should the `verify:` predicate mechanism actually check, and how do you *quantify*
claim drift rather than merely label it?

**Headline finding:** the algorithm is already in this repo, pointed outward. `spring_drift_check.py`
does content-signature plus syntax-aware recheck against a *target* repo's evidence. Turning that on
this repo's own claims is mostly reuse, not invention.

---

## 1. The problem is real and near-universal — and the on-point research is deterministic

**Tier A, verified at `arxiv.org/abs/2212.01479`** — *Detecting Outdated Code Element References in
Software Repository Documentation*, Wen Siang Tan, Markus Wagner, Christoph Treude, 2022-12-02.

- Method: **deterministic static analysis**, detecting "code element references that survive in the
  documentation after all source code instances have been deleted."
- Scale: **over 3,000 GitHub projects**.
- Finding: **"most projects contain at least one outdated code element reference at some point in
  their history."**

Two things follow. This repo is not unusually sloppy — it is unusually *instrumented*, which is why
its drift is visible at all. And the paper aimed squarely at this problem is **not** machine
learning.

**Worth stating, because it looks like a gap otherwise:** the mainstream of the code-comment
inconsistency literature *is* ML — BERT/Longformer NLI framings (`arXiv:2207.14444`), CodeT5+ over
structured diffs (`arXiv:2512.19883`), sequence-to-sequence comment updaters. This repo sits in the
deterministic corner deliberately, not through ignorance of that work: a probabilistic verifier
would put a model in the trust path of the mechanism whose entire job is to be the thing you can
trust when the model is wrong. (Tier B — these three are search-level; only `2212.01479` was opened.)

**The taxonomy worth borrowing:** the literature splits **just-in-time** (prevent an inconsistency at
change time) from **post-hoc** (find the ones already there). Both are needed here and they are
different products: CI-gating a PR is JIT; sweeping the existing corpus is post-hoc. `verify:` in CI
is the JIT half. Nothing does the post-hoc half yet.

## 2. The predicate model — in-toto

`in-toto/attestation` (356★, pushed 2026-07-21). Two fields: a `predicateType` **URI**, and a
`predicate` body. The architectural point is the **separation of subject from claim** — the Statement
layer holds the `subject` being attested; the predicate layer holds "arbitrary metadata about the
subject." `predicateType` is a URI so types namespace and extend without collision.

**Applied here:** the current syntax conflates the two into one string —

```
verify:
  - path_exists:.ruff.toml
```

— where `path_exists` is the predicate type and `.ruff.toml` is the subject. That is fine while there
are four predicates and no arguments. It stops being fine the moment a predicate needs *parameters*
(a signature, a window, an expected value), because there is nowhere to put them. Splitting subject
from predicate before that happens is cheap; retrofitting it later means rewriting every claim.

## 3. The drift mechanism — fiberplane/drift

122★, pushed 2026-06-22. **Below `00`'s 300–500 triage floor**, kept deliberately under `00`'s own
"don't discard a smaller, precisely on-point repo without actually checking it" — and this repo
already cites it in `CONSTRAINTS.md` as the prior art for multi-baseline resolution.

Its model, quoted from the README:

- A binding is **Path** + optional **Symbol** (`#Name`, narrowing to a declaration) + **Signature**
  ("content fingerprint stamped by `drift link`").
- Docs can carry inline references: `@./src/auth/provider.ts#AuthConfig`.
- The fingerprint is **syntax-aware**: "drift parses with tree-sitter and hashes a normalized AST
  fingerprint (node kinds + token text, no whitespace or position data)."
- `drift check` recomputes and compares, reporting e.g.
  `STALE src/auth/provider.ts#AuthConfig (changed after doc)`.

The AST-normalized fingerprint is the part worth stealing: **reformatting does not false-positive.**
A checker that cries wolf on whitespace gets disabled, which is the failure mode that matters more
than any missed detection.

## 4. This repo already implements that algorithm — outward

| drift's mechanism | this repo's existing equivalent |
|---|---|
| content fingerprint per binding | `spring_signal_scan.py`'s `file_signatures` |
| syntax-aware recheck | `spring_drift_check.py` tier 2 — targeted `ast-grep` re-run |
| cheap first pass | `spring_drift_check.py` tier 1 — content hashes |
| `drift check` verdicts | `drift_report.json` statuses (`unchanged`, `confirmed_still_present`, `drifted`, `file_deleted`) |
| tree-sitter | **`ast-grep`, already a pinned dependency** |

So the verify algorithm needs no new engine and no tree-sitter. It needs the existing two-tier
detector aimed at a different subject: this repo's own claims rather than a target repo's evidence.
That is the `00` "reuse rather than rediscover" case, and it is unusually clean here because the
tiering — cheap hash first, expensive syntax-aware recheck only on the changed set — is exactly what
keeps a claim-checker fast enough to stay wired in.

## 5. The predicate algebra: three classes exist, the fourth is missing

| Class | Predicate | Status | Catches |
|---|---|---|---|
| Existence | `path_exists`, `path_absent` | **have** | prompt `07`'s stale `status:`, `CONSTRAINTS.md` citing a deleted script, `12` naming absent files |
| Content | `contains:` | **have** | a doc that no longer states what it must |
| Derived equality | `derived:` | **have** | a committed count that no longer recomputes |
| **Stability** | `unchanged_since:<signature>` | **missing** | the referent moved while the prose did not |

The fourth class is the one the entire drift literature is about, and it covers the residue the other
three cannot reach: **prose claims that are not reducible to a computable value.** For those you
cannot verify *truth* — but you can detect that the thing being described *changed since the claim
was last affirmed*, which is a staleness signal rather than a truth verdict, and is honest about
being one.

That distinction is the whole design. `derived:` says "this number is wrong." `unchanged_since:` says
"nobody has re-read this since the code moved." The second is weaker and far more widely applicable,
and conflating them would produce either false confidence or false alarms.

## 6. Quantifying drift

Once a claim carries `{subject, predicate, status, last_affirmed}`, four numbers become computable —
and they are the instrument for deciding *when drift actually matters*, rather than treating every
stale sentence as equally urgent:

- **Unfalsifiable ratio** — share of claims carrying no predicate at all. Probably the single most
  useful number here, and currently unknown. A claim nothing can check is not a weak claim; it is
  not a claim.
- **Pass rate** among those that can be checked.
- **Staleness distribution** — age since last affirmation. A `[Resolved]` from three months ago that
  nothing has re-checked is a different object from one affirmed this morning.
- **Count by status** — which alone would have caught `CONSTRAINTS.md`'s vocabulary sprawling from
  the **3** words `CLAUDE.md` documents to the **15** now present.

## 7. Design cautions

- **Do not invent a fifth syntax.** Four prose-annotation vocabularies already exist here — evidence
  tags, derived blocks, `verify:` frontmatter, and `CONSTRAINTS.md`'s bracket tags. `verify:` is the
  right host; extend it.
- **Split subject from predicate now**, before any predicate needs parameters.
- **Stay deterministic.** The on-point paper is; the repo's ethos is; and a model in the trust path
  of the verifier defeats the verifier.
- **Tier the checks** — cheap hash first, syntax-aware recheck only on what changed. Not an
  optimisation: it is what keeps the check fast enough that nobody switches it off.
- **The post-hoc sweep is a separate deliverable** from the JIT gate, and is currently absent.

## Open frontier

- `00`'s DeepWiki cross-check was **not** run for `fiberplane/drift`.
- Three ML papers are cited at search-snippet level only (Tier B); none were opened. They are cited
  to place this repo's deterministic choice in context, not as support for any mechanism here.
- `unchanged_since:` has no prototype. The nearest working code is `spring_drift_check.py`'s tier
  1/tier 2 split, which is the thing to adapt rather than a thing to copy.
