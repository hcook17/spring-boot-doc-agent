# Contributing

## Local pre-PR gate (principal-engineer push hook)

Before opening a PR, push is the practical choke point (`gh pr create` cannot be
hooked by git). Enable the committed hooks once per clone:

```bash
git config core.hooksPath .githooks
```

`.githooks/pre-push` runs `python scripts/ci/pre_pr.py --auto` (path-risk
routing over the same hard suites CI runs). Details and tiers:
[`scripts/README.md`](scripts/README.md).

When GitHub Actions is unavailable, use
`python3 scripts/ci/pre_pr.py --actions-outage` for hermetic CI parity (CodeQL +
certification verify); procedure under **Actions outage** in
[`scripts/README.md`](scripts/README.md). That receipt is interim — re-run CI on
the same SHA when Actions recovers.

Emergency bypass (always logged under `.git/pre-pr-bypass.log`):

```bash
PRE_PR_SKIP=1 PRE_PR_SKIP_REASON='short justification here' git push
```

`PRE_PR_SKIP` alone is rejected. Prefer fixing the failing suite.

## Write-then-verify: never trust a write tool's success response alone

**Rule:** after any file write made through a device bridge, remote tool, or subagent whose only view of the filesystem is a bridged connection, the very next action is re-reading that file's actual content directly. A "written" response, a byte count, or a reported mtime is not evidence the live file changed — only a direct re-read is.

**Why this rule exists, not just what it says:** this repo has two confirmed, independent incidents of the same failure shape — trusting a tool's or document's account of state instead of re-verifying it directly:

1. A cloud sandbox session driving this repo through a device-file-bridge tool had that bridge repeatedly report a file as "written" when the live copy on disk hadn't actually changed. Caught only by re-reading the file's actual bytes after a "success" response, and re-discovered more than once because each new session initially trusted the tool's own response instead of checking. See `IMPLEMENTATION_HANDOFF.md`'s opening section for the full account.
2. A later, unrelated incident: a memoryless session trusted a handoff document's stale claim about repo state (that certain files were still untracked) rather than checking actual repo state (`git status`, `gh pr view`) directly, and committed files onto the wrong branch as a result. Logged in `claude/session-log.md` (2026-07-23, "Stray scaffolding commit landed on the wrong branch").

Same root cause both times — trusting a tool's or a document's *report* of state instead of the state itself — different surface (file content vs. git/PR state). The rule below is written broadly enough to cover both.

**How to apply it:**

- Local filesystem calls made directly by a Claude Code CLI session against a repo checked out on that same machine (the normal case for this repo) are not the failure mode described above — there is no bridge in that path. The rule exists for the cases that *do* have an intermediary: a device bridge, a remote/cloud sandbox tool, or any handoff where one session's account of "this is done" is the only thing a later session has to go on.
- Before treating any prior session's, document's, or tool's claim about current repo state as fact — "this file was already fixed," "these files are untracked," "this test suite passes" — re-check it directly (`git status`, a direct file read, an actual test run) rather than building further work on top of an unverified claim. `IMPLEMENTATION_HANDOFF.md`'s own "Step 0 — Reconcile against the known-good baseline" is a worked example of this: it does not assume its own bundled baseline files are already live in the repo, it says to diff and confirm first.
- If you are automating verification (rather than doing it by hand) inside this repo's own Claude Code plugin tooling, the supported mechanism is a `PostToolUse` hook matched against `Write|Edit` (see `code.claude.com/docs/en/hooks` and `plugins-reference`'s hook-matcher documentation) — Claude Code's own docs don't document any built-in guarantee that a write tool's reported success reflects the live file, so a hook is the place to add that guarantee yourself if you need it enforced automatically rather than as a manual checklist step. No such hook exists in this repo as of this writing; this paragraph documents the mechanism, not a claim that it's wired in.

Research note (per `claude/steering-prompts/05-clarity-delivery-trust-research-prompt.md`): a GitHub search for small, well-maintained "write-then-verify" or checksum-confirm utilities turned up nothing genuinely on-point — the closest matches (`teran/checksum`, `nicjansma/checksum-verifier`, and similar) solve a different problem (verifying a *downloaded* file's integrity against a known-good checksum), not "did my own write tool's success response reflect what's actually on disk." Per the shared research standard, finding nothing better than "read the file back after writing it" is itself a valid result — that's the rule stated above, codified as an explicit checklist step rather than left as tribal knowledge.

## Module docstrings: reference first, rationale second

**Rule:** a module docstring opens with one sentence saying what the module *is*, then — for any
module with a `__main__` entry point — a `Usage:` block within the first 15 lines. Everything else,
including the full argument for why the module exists, goes *after* that. Comments follow the same
shape: one line saying what the code does, then the justification.

**Why this rule exists, not just what it says:** the reasoning in this repo's scripts is genuinely
valuable and is *not* the problem. Measured across `scripts/` on 2026-07-25: 35 module docstrings,
1,481 lines, mean 42. `spring_drift_check.py` ran to 202 lines with its `Usage:` block at **line
193**; `spring_signal_scan.py` to 152 lines with no usage block at all. Nine modules had none;
fourteen buried it past line 20. Someone who just wants to run the thing reads an essay first.

The density itself is deliberate and worth keeping — `.ruff.toml` sets the line limit from this
repo's own distribution precisely because 38–54% of the larger modules is explanatory prose. **This
rule deletes no reasoning.** It orders it: the reader gets a hook to hang the argument on before the
argument arrives. A skimmer reads line one and leaves; a deep reader keeps going and finds
everything that was there before.

**How to apply it:**

- Order is `what` → `how to run` → `why`. The `WHY THIS EXISTS` heading already used by
  `check_pipeline_output.py` and `check_code_quality.py` is the right marker for the third part.
- **Library modules with no CLI are exempt from the `Usage:` requirement** and should not invent one.
  `doc_tag_utils.py`, `_shared_excludes.py`, `_config_keys.py` and `_secret_heuristics.py` are
  imported, never run; demanding a usage block from them would be a check pointed at the wrong thing.
- Lead a comment with what it does, then justify: `# `bare` matches unbackticked repo paths.` before
  the paragraph explaining which incident made that necessary. The justification is why the comment
  survives review; the summary line is why anyone can skim past it.
- This is enforced, not merely encouraged: `scripts/ci/check_code_quality.py` fails when a module with a
  `__main__` entry point has no `Usage:` block near the top. It ratchets against
  `scripts/ratchets/code_quality_baseline.json`, so modules that predate the rule are recorded rather than
  blocking, and no *new* violation can land.

**On the "near the top" number, and re-deriving it.** `USAGE_WITHIN_LINES = 20` was read off this
repo's own distribution, which is bimodal: twelve modules state the command by line 18, thirteen bury
it at line 29 or later, and nothing sits in between. In the threshold-derivation literature's terms
that is *unsupervised natural-breaks clustering on a single system* — the weakest available basis.
The canonical unsupervised method (Alves, Ypma & Visser, ICSM 2010) aggregates across a benchmark of
~100 systems precisely because single-system thresholds are unstable; supervised methods key the
cut-point to a measured outcome, which needs labels this repo does not have.

So the number is a fact about the current tree, not a constant. **Re-derive it when the tree changes**
rather than defending it:

```bash
python - <<'PY'
import ast, pathlib, re
U = re.compile(r"^\s*(usage|run with|run)\s*:", re.I)
pos = []
for p in sorted(pathlib.Path("scripts").glob("*.py")):
    doc = ast.get_docstring(ast.parse(p.read_text(encoding="utf-8")))
    if not doc:
        continue
    for i, line in enumerate(doc.splitlines()):
        if U.match(line):
            pos.append(i + 1)
            break
print(sorted(pos))
PY
```

Look for the gap; put the threshold inside it. If the distribution stops being bimodal, this check
has stopped measuring something real and should be reconsidered rather than retuned.

## Line coverage ratchet

CI measures statement+branch coverage for the installable packages `doc_engine`
and `stf` (not `scripts/` or `adapters/`) and fails if the combined total drops
below `[tool.coverage.report] fail_under` in `pyproject.toml`. Ratchet upward by
editing that one number after a deliberate coverage gain. Delete local
`.coverage*` files before measuring if you previously collected statement-only
data — mixing them with `branch = true` makes coverage refuse to combine.

Locally (after `pip install -r requirements-dev.txt` and `pip install -e .`):

```bash
rm -f .coverage .coverage.* coverage.xml
pytest tests/ -q --cov=doc_engine --cov=stf --cov-branch --cov-report=term-missing
```

CI also uploads `coverage.xml` from the Python 3.11 matrix cell. The hard
**Coverage on New Code** gate is `diff-cover` in the `quality-gates` job (below),
not SonarCloud. The overall `fail_under` floor (82) stays separate.

## In-repo quality gates

SonarCloud **Free** cannot customize Quality Gate thresholds. Policy is enforced
in GitHub Actions by the `quality-gates` job in `.github/workflows/ci.yml`, which
runs `scripts/ci/run_quality_gates.py` after the `test` job publishes
`coverage-xml`.

### Evidence table (2026-qualified tools only)

Audited against GitHub/PyPI on 2026-08-08. Rejected without 2026 push **or**
release: radon, xenon, Melevir/`cognitive_complexity`, and other pre-2026
zombies. Metric research framing: Campbell cognitive complexity (TechDebt 2018);
empirical understandability work on arXiv ([2007.12520](https://arxiv.org/abs/2007.12520),
[2303.07722](https://arxiv.org/abs/2303.07722)); coupling/churn/bus-factor as
review concerns ([2310.03673](https://arxiv.org/abs/2310.03673),
[2401.03303](https://arxiv.org/abs/2401.03303)).

| Gate | Tool | Stars (≈) | Latest release | Last push | Metric type | CI behavior |
| --- | --- | --- | --- | --- | --- | --- |
| New-code coverage ≥ **98.7%** | [diff-cover](https://github.com/Bachmann1234/diff_cover) `~=10.5.0` (+ pytest-cov XML) | 843 | **v10.5.0** (2026-08-08) | 2026-08-08 | Diff line coverage vs compare ref | **hard fail** |
| Duplication ≤ **3%** | [jscpd](https://github.com/kucherenko/jscpd) `@5.0.14` via `npx` | 5980 | **v5.0.14** (2026-07-27) | 2026-08-07 | Token clone % on **changed** `src/doc_engine` + `src/stf` `.py` | **hard fail** |
| Complexity ≤ **5** / function | [complexipy](https://github.com/rohaquinlop/complexipy) `~=6.2.0` | 748 | **6.2.0** (2026-07-23) | 2026-08-04 | Cognitive complexity (Campbell/Sonar-inspired; not affiliated with Sonar) | **hard fail** on offender-count ratchet (`scripts/ratchets/complexipy_baseline.json`) until count reaches 0 |
| Import cycles / coupling | [tach](https://github.com/tach-org/tach) `~=0.35.0` | 2785 | **v0.35.0** (2026-05-12) | 2026-06-11 | `forbid_circular_dependencies` (`tach.toml`) | **hard fail** |
| Soft McCabe backup | [ruff](https://github.com/astral-sh/ruff) C901 (already pinned `~=0.16.0`) | 49k+ | 2026 releases | 2026-08-08 | Cyclomatic (McCabe) — **not** cognitive | optional / not selected in `.ruff.toml` |
| Security signal | Semgrep + CodeQL (existing CI jobs) | — | — | — | SAST | unchanged hard jobs |
| SonarCloud | scanner job kept | — | — | — | Dashboard signal | **non-blocking** (`continue-on-error`) |

**import-linter** also 2026-PASS (PyPI 2.13 uploaded 2026-07-03; push 2026-08-07) but is not wired — tach alone owns the cycle gate.

**Complexity remediation.** Policy target is ≤5 cognitive complexity per function on all of `src/doc_engine` + `src/stf`. While legacy offenders remain, CI hard-fails when the offender *count* rises vs `scripts/ratchets/complexipy_baseline.json` (ratchet downward after each remediation batch; never raise it). Prefer named helpers and early returns over micro-fragmentation; do not weaken the ≤5 threshold.

### Local run

```bash
pip install -r requirements-dev.txt && pip install -e .
# after a coverage.xml exists from pytest --cov ...
python3 scripts/ci/run_quality_gates.py --compare-ref origin/main
```

### Deferred (no fake CI gates)

| Taxonomy item | Status |
| --- | --- |
| Halstead / Maintainability Index / essential complexity | **Deferred** — radon/xenon lack 2026 releases/pushes |
| Big-O time/space | **Deferred** — not statically enforceable; ADR/review |
| LCOM / full cohesion suites | **Deferred** — no 2026-maintained Python CI tool selected |
| Fan-in/out scores as thresholds | **Deferred** — tach cycles only for now |
| Code churn as bug predictor | **Deferred** — needs history heuristics, not a merge gate |
| Bus factor | **Deferred** — blame/ownership analysis ([2401.03303](https://arxiv.org/abs/2401.03303)), not CI |
| Sonar custom Quality Gate | **Deferred on Free** — cannot set 98.7% / 3% / complexity in UI |

## SonarCloud (soft signal only)

The `sonarcloud` job still uploads analysis for the dashboard but is
**non-blocking**. Free-plan Quality Gates are not the source of truth for the
thresholds above — `quality-gates` is. Keep `SONAR_TOKEN` if you want the
dashboard; turn Automatic Analysis **OFF** if you run CI analysis (dual-method
error otherwise). `sonar.qualitygate.wait` is off in CI on purpose.

In-repo Sonar parameters remain in `sonar-project.properties`
(`sonar.python.coverage.reportPaths`, coverage exclusions for `adapters/**` /
`scripts/**`, `relative_files = true` under coverage).

## Current status and steering prompts

See `STATUS.md` for a current-state snapshot of this plugin (what's done, what's pending, next concrete action) and `claude/session-log.md` for the append-only history of commits that affect the assumptions in `claude/steering-prompts/`. `CLAUDE.md` explains when a commit needs a session-log entry.
