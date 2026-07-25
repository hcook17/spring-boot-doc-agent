---
category: Dependency pinning (not a research prompt — implementation task)
status: [Resolved — 2026-07-25] `requirements.txt` added at plugin root pinning `ast-grep-cli~=0.45.0`, `sqllineage~=1.5.8`, `pathspec~=1.1.1`; `.github/workflows/ci.yml` updated to `pip install -r requirements.txt`. See `CONSTRAINTS.md` "Runtime prerequisites" item 4 and `claude/session-log.md`'s 2026-07-25 pinning entry.
related: CONSTRAINTS.md "Runtime prerequisites" items 1-4, MATURITY_ASSESSMENT.md "Dependency reproducibility" scorecard row and adoption gate checklist, .github/workflows/ci.yml
verify:
  - contains:requirements.txt:ast-grep-cli
  - contains:requirements.txt:sqllineage
  - contains:requirements.txt:pathspec
  - contains:.github/workflows/ci.yml:requirements.txt
---

# Task prompt: pin this plugin's three unpinned third-party dependencies

Self-contained — read this without assuming any other conversation's context.

Context: `spring-boot-doc-agent` (this repo) depends on three third-party things — the `ast-grep` binary/its pip wrapper `ast-grep-cli`, `sqllineage`, and `pathspec` — none of which are version-pinned anywhere in the repo. No `requirements.txt` or `pyproject.toml` exists. `.github/workflows/ci.yml`'s "Install Python dependencies" step is a single unpinned line: `pip install ast-grep-cli sqllineage pathspec` (no version specifiers at all).

This was a theorized risk until 2026-07-24, when a reviewer's fresh-environment test run empirically confirmed it, per `CONSTRAINTS.md`'s "Runtime prerequisites" items 1/2/4: `test_capacity_preflight.py` failed **outright** without `ast-grep` on `PATH` (that suite imports `spring_signal_scan`, which shells out to it), and `test_spring_signal_scan.py` failed **7/32** without `sqllineage` installed (not a silent field-level degrade, as item 2 previously — incorrectly — described it; an actual test failure). Installing both brought every suite to a clean pass. `pathspec` is a genuinely soft dependency (`--respect-gitignore` opt-in only) and wasn't implicated in that specific failure, but is equally unpinned. `MATURITY_ASSESSMENT.md`'s adoption gate checklist already marks this item **"blocking, not aspirational"** based on that finding — this task is what actually closes it.

## Do this

1. **Add a single `requirements.txt` or `pyproject.toml` at the plugin root** (pick one — don't add both; this repo has no existing Python packaging convention to match, so either is a legitimate minimum-viable choice, but adding both would just be two sources of truth for the same thing). Pin `ast-grep-cli`, `sqllineage`, and `pathspec` to specific, currently-verified-compatible version ranges.

   **Check current versions yourself — don't guess or carry forward a number from this prompt, since none is given here on purpose.** Concretely: `pip index versions ast-grep-cli`, `pip index versions sqllineage`, `pip index versions pathspec` (or `pip show <pkg>` after installing latest, to confirm what CI's current unpinned line actually resolves to today) before picking a pin. Prefer a compatible-release specifier (`~=`) over an exact `==` pin unless you have a specific reason to pin exactly — the goal is "a fresh environment reliably gets a working version," not "never allowed to move."

2. **Update `.github/workflows/ci.yml`'s "Install Python dependencies" step** (currently line 37: `pip install ast-grep-cli sqllineage pathspec`) to install from the new pinned file instead (`pip install -r requirements.txt`, or the `pyproject.toml` equivalent).

3. **Update `CONSTRAINTS.md` item 4** to `[Resolved]` once pinning lands — replace "None of the above are version-pinned anywhere in the repo" with a pointer to the new file, and keep the existing 2026-07-24 empirical-finding sentence intact (don't delete the evidence, just mark the gap it describes as closed).

4. **Update `MATURITY_ASSESSMENT.md`**: change the "Dependency reproducibility" scorecard row's rating (currently `**Weak — now empirically demonstrated, not just theorized**`) to reflect the fix, and check off the adoption gate checklist's "Dependencies pinned" item.

5. **Append a `claude/session-log.md` entry** cross-referencing `claude/steering-prompts/03-constraints-research-prompt.md` — this change doesn't touch `scripts/`/`agents/`/`skills/`/`references/` directly, so `CLAUDE.md`'s trigger condition for a mandatory entry doesn't strictly apply, but this session's own precedent (see the 2026-07-24 "fresh-environment dependency failure empirically confirmed" entry) was to log constraint-related findings anyway, for continuity.

## What NOT to do here

- Don't introduce a virtualenv/poetry/pipenv toolchain, or any dependency manager beyond a plain `requirements.txt`/`pyproject.toml` — this repo is otherwise stdlib-first with plain `pip install`, and anything heavier is over-engineering relative to what's actually broken, per `claude/steering-prompts/00-shared-research-standards.md`'s "what scaffold and implement means" (no new infrastructure beyond what's already assumed).
- Don't try to pin the `ast-grep` Rust/cargo binary itself, or touch the `cargo install ast-grep` / `npm install -g @ast-grep/cli` mentions elsewhere in the repo's docs (`README.md`, `CONSTRAINTS.md` item 1) — CI only ever installs the pip-packaged `ast-grep-cli` wrapper; pin that one thing, don't introduce a second install path or rewrite documentation about a path this task doesn't touch.
- Don't remove or weaken the existing graceful-degrade behavior for `sqllineage`/`pathspec` (`try`/`except ImportError` at their call sites in `scripts/spring_signal_scan.py` and `scripts/partition_repo.py`) — pinning a version in a lockfile is orthogonal to whether the import stays soft at runtime. It should stay soft; you're only making "if installed, which version" deterministic, not making the import mandatory.
- Don't retrofit branch protection or required reviews into this task (`CONSTRAINTS.md`'s "Enterprise-readiness gaps" item 6) — a separate, already-tracked, deliberately-deferred repo-admin action with its own blast radius.

## Verification

Re-run all nine existing test suites plus the meta-verification script, against the newly-pinned versions: `test_spring_signal_scan.py`, `test_partition_repo.py`, `test_spring_drift_check.py`, `test_pipeline_stages.py`, `test_secret_heuristics.py`, `test_config_keys.py`, `test_semantic_eval_helpers.py`, `test_capacity_preflight.py`, `test_verify_llms_docs.py`, and `scripts/verify_llms_docs.py`. Report every pass count, not just "tests passed."

Critically, also re-run **the actual fresh-environment repro that surfaced this gap** — a clean venv or container with none of the three dependencies preinstalled, following only the new pinned-install instructions (`pip install -r requirements.txt` or the `pyproject.toml` equivalent, plus whatever `ast-grep` binary install step `README.md` already documents) — to confirm the fix actually resolves the empirical finding (no more outright failure in `test_capacity_preflight.py`, no more 7/32 failures in `test_spring_signal_scan.py`), not merely that a pinning file now exists in the repo.

Commit on a new branch off `main`, per this repo's usual one-branch-per-concern convention. Open a PR, report back the PR URL, every test suite's pass count, and confirmation that the fresh-environment repro was actually re-run (not skipped as "should be fine now").
