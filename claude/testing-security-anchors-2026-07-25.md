# Testing, security and reliability anchors — research, 2026-07-25

Researched to `claude/steering-prompts/00-shared-research-standards.md`'s bar (arXiv confirmed to
resolve *and* to say what is claimed of it; GitHub filtered on star count **and** push recency;
every claim tagged confirmed-via-primary-source-I-opened versus plausible-but-unverified), with
`10-review-persona-and-standards.md`'s Tier A/B/C vocabulary.

## Why this exists

`10-review-persona-and-standards.md` §5 anchors DDIA the useful way: *"the epub is in the project;
do not re-derive these, cite them."* There is no equivalent for testing or security, and the cost
shows up as re-derivation:

- **Testing.** This repo verifies test non-vacuity by hand, in PR after PR — neutering
  `check_pipeline_output.exit_code` to confirm five tests went red; reverting the `capacity_preflight`
  path fix to confirm three failed; reverting the `run_ast_grep` exception fix to confirm five errored
  with `SystemExit: 1`. Each was correct, each was done once, and none is repeatable. That ritual has
  a name and a tool (below).
- **Security.** `scripts/verify_llms_docs.py` extracted backtick-fenced spans from LLM-authored
  markdown and passed them to `bash -c` with `GH_TOKEN` in scope. It was found, reproduced, and
  deleted — correctly. It also has a standard name, which this repo never used, because it had no
  security vocabulary to reach for.

An anchor list does not prevent either failure. It removes the excuse of having to reason from first
principles each time.

---

## The reading stack

Two picks per domain, following the "reference heavyweight" versus "actually read this in 2026"
split, plus one book that spans reliability and security.

| Role | Book | Verification | Free full text |
|---|---|---|---|
| **Security heavyweight** — the DDIA analogue | *Security Engineering: A Guide to Building Dependable Distributed Systems*, 3rd ed., Ross Anderson, Wiley 2020, 29 chapters | **Tier A** — author's own page, `cl.cam.ac.uk/~rja14/book.html` | **Yes** — all chapters as free PDFs after a stated 42-month embargo; 1st and 2nd editions also free |
| Security, practical | *Alice and Bob Learn Secure Coding*, Tanya Janca, Wiley, **11 Feb 2025**, 416pp, ISBN 9781394171705 | **Tier A** — Wiley listing | No |
| **Testing reference** | *xUnit Test Patterns: Refactoring Test Code*, Gerard Meszaros, Addison-Wesley 2007, ISBN 9780131495050 — 68 patterns, 18 test smells | **Tier A** bibliographic | `xunitpatterns.com` is the author's free companion catalogue — **Tier B, not verified by me**: the site is HTTP-only and refused the upgraded request |
| Testing, practical | *Unit Testing: Principles, Practices, and Patterns*, Vladimir Khorikov, Manning | **Unverified** — do not cite until checked | No |
| Reliability + security | *Building Secure & Reliable Systems*, Adkins, Beyer, Blankinship, Oprea, Lewandowski, Stubblefield | **Tier A** — `sre.google/books` | **Yes** |

**Why Anderson is the right DDIA analogue, and it is not only about merit.** DDIA earns its role in
`10` §5 because the text is *present and citable* — an anchor you cannot open is a paraphrase waiting
to drift. Security Engineering is the only security heavyweight where free, complete, permanent
availability is true, so its chapters can be cited the way DDIA's are rather than summarised from
memory. *Building Secure & Reliable Systems* has the same property and covers the reliability axis.

**On the newer Janca book.** The commonly-cited title is *Alice and Bob Learn Application Security*
(Wiley 2020, ISBN 9781119687405). *Secure Coding* (Feb 2025) is the newer work and the better
"read this in 2026" pick; it is a different book, not a second edition.

---

## The anchor that names this repo's own history

**OWASP Top 10 for Large Language Model Applications.** Three entries map onto this codebase directly:

- **Insecure Output Handling** — exactly the deleted `verify_llms_docs.py`: model-authored text
  flowing into an interpreter. Having the category name available would have classified that defect
  on sight instead of by reproduction.
- **Excessive Agency** — the five pipeline subagents hold `Write`, and `check_pipeline_output.py`'s
  write-scope check is the compensating control. `CONSTRAINTS.md` already records that the check is
  blind to gitignored paths, which is an Excessive Agency gap stated in its own terms.
- **Prompt Injection** — Stage 1 reads a target repository's source, which is untrusted input, into
  agent prompts. This is the pipeline's structural exposure and it is currently unmitigated by design.

> ⚠️ **Version pin unresolved — do not cite an `LLMxx` number from this document.** `00` requires
> version-pinning every version-sensitive claim. The OWASP project page presents **2025** as current,
> while the content retrieved on 2026-07-25 enumerated the **v1.1** identifiers. The 2025 edition
> renumbers the list. The category **names** above are safe; the **numbers** are not. Resolve against
> the 2025 PDF before citing an identifier.

---

## Empirical grounding

**Tier A, verified at `arxiv.org/abs/1704.08412`** — *A Large-Scale Study on the Usage of Testing
Patterns that Address Maintainability Attributes*, Gonzalez, Santos, Popovich, Mirakhorli, Nagappan,
submitted 2017-04-27.

Scope: **82,447 open-source projects** across **251 testing frameworks** (93 actively used). Findings:
only **17% of projects had test cases at all**; of those, **24%** used maintainability-oriented
patterns; and pattern adoption was *"an ad-hoc decision by individual developers, rather than
motivated by the characteristics of the project."*

**Stated limit, because the temptation is to overclaim:** the abstract does **not** cite Meszaros. It
examines four xUnit patterns, so it supports *"these patterns exist and are unevenly, unsystematically
adopted"* — it does **not** validate the xUnit Test Patterns catalogue, and must not be cited as doing
so. The distinction matters here for the same reason `00` insists on it: this project has previously
had a Tier C source treated as Tier A.

---

## Tooling

All figures from the GitHub REST API on **2026-07-25**, not from a blog or a listicle.

| Repo | Stars | Last push | Read |
|---|---:|---|---|
| `gitleaks/gitleaks` | 28,297 | 2026-07-22 | Both signals strong |
| `trufflesecurity/trufflehog` | 27,197 | 2026-07-24 | Both strong |
| `semgrep/semgrep` | 16,006 | 2026-07-24 | Both strong |
| `pytest-dev/pytest` | 14,368 | 2026-07-24 | Both strong |
| `HypothesisWorks/hypothesis` | 8,818 | 2026-07-24 | Both strong |
| `PyCQA/bandit` | 8,182 | 2026-07-21 | Both strong |
| `boxed/mutmut` | 1,357 | 2026-07-16 | Modest stars, active, precisely on-point — kept under `00`'s "don't discard a smaller, precisely on-point repo" |
| `pypa/pip-audit` | 1,340 | 2026-07-24 | Modest stars, but PyPA-official and active |
| `sixty-north/cosmic-ray` | 645 | 2026-04-02 | ~4 months stale; state that explicitly if ever used |

**Open frontier, not silently skipped:** `00` also requires a DeepWiki cross-check for every repo that
becomes a serious candidate. That was **not performed** for `mutmut` or `gitleaks`. Anyone acting on
those two should do it first.

### The finding worth acting on

**Mutation testing is the missing mechanical control for this repo's most-repeated manual ritual.**
The hand-verification described at the top of this document — break the code, confirm the tests go
red, restore it — is mutation testing, executed by a human, once, with no artifact proving it was
ever done. `mutmut` automates precisely that, and it is the natural enforcement mechanism for the
standing rule that *a gate that cannot be shown to fail is not a gate*. The rule currently depends on
each author remembering to perform the ritual and to write down the result honestly.

Two smaller ones:

- `hypothesis` is the tool-shaped form of a finding this repo already made and measured: **invariants
  beat re-run-and-diff probes**. A determinism probe passed against an unfixed scanner while
  `keys == sorted(keys)` caught it. Property-based testing is that lesson generalised.
- The 2026-07-25 `.gitignore` leak — a public ignore rule naming a client service — was caught by a
  human reading a diff, and `CONSTRAINTS.md` now records that nothing mechanical looks for it.
  `gitleaks` is the right *category*, but **be precise: it detects secrets, not client names.** Closing
  that specific hole needs a custom deny-list rule; adopting gitleaks unmodified would produce a green
  check that does not cover the actual failure — which is its own anti-pattern here.

---

## OIDC — checked, and the answer today is "no, but record the trigger"

Assessed 2026-07-25 because the question came up. All three plausible uses are currently empty:

| Use | State |
|---|---|
| Replace long-lived secrets | **Nothing to replace.** `gh api repos/.../actions/secrets` returns `count=0`. The only credential in CI is `${{ github.token }}`, the ephemeral per-run token, and `permissions:` is already least-privilege (`contents: read`, `pull-requests: read`). |
| Federate to a cloud provider | No cloud resources in CI. |
| Build-provenance attestation | **Nothing to attest.** 0 releases, 0 tags. The plugin is consumed as a git checkout (`claude plugin marketplace add ./spring-boot-doc-agent`), not as a built artifact. |

Adopting it now would import complexity for its own sake, which `00` explicitly warns against. What is
worth recording is that **the default path at each trigger point is the insecure one**:

- **If the repo starts cutting releases** → attest build provenance, so a consumer can run
  `gh attestation verify <artifact> -R hcook17/spring-boot-doc-agent`. GitHub's docs give the required
  permissions as `id-token: write`, `contents: read`, `attestations: write`. (*`id-token: write` is the
  OIDC token-request permission — that identification is mine; the page fetched did not itself name
  OIDC or Sigstore.*) This matters more than usual because the plugin executes on other people's
  machines, and it maps to the OWASP supply-chain category above.
- **If a `pyproject.toml` ever leads to PyPI publishing** → use PyPI **Trusted Publishing** via OIDC
  *instead of* storing an API token as a repository secret. Flagged specifically because the Python
  version normalisation work adds a `pyproject.toml`, which makes publishing an easy next step and a
  stored token the path of least resistance.

---

## What this does not do

It does not make the repo more secure or better tested by existing. It gives future sessions something
to cite, and it records three things that were verified so they are not re-derived: that Anderson and
the Google book are free and therefore citable, that the arXiv paper says less than it is tempting to
claim, and that OIDC currently has nothing to attach to here.
