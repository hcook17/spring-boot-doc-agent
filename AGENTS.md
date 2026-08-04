# AGENTS.md

For repo working conventions (steering prompts, session log, `ast-grep`-only
search mandate, state-claim gates), read `CLAUDE.md` first — it is the source of
truth and applies to every session.

## Cursor Cloud specific instructions

This is a **pure Python 3.10+ project** (the `doc-engine` CLI/SDK). There is no
web server, database, or other networked service — it is a CLI tool plus
optional adapters. Standard install/lint/test/run commands live in `README.md`
and `.github/workflows/ci.yml`; prefer those over duplicating them here.

### Environment layout

- Dependencies are installed into a virtualenv at `.venv/` (gitignored). The
  startup update script refreshes it. Activate it before running anything:
  `. .venv/bin/activate` (this puts `doc-engine`, `pytest`, `ruff`, `ast-grep`,
  and `semgrep` on `PATH`). Equivalently call binaries directly, e.g.
  `.venv/bin/pytest`.
- `ast-grep` and `semgrep` must be the exact pinned versions from
  `requirements.txt` on `PATH`; CI fails if a differently-versioned system
  install shadows the venv one. Inside the activated venv the pinned versions
  win — check with `which -a ast-grep` if a version gate ever complains.

### Common commands (run inside the activated venv)

- Lint: `python3 -m ruff check --no-cache scripts/ src/doc_engine/`
- Tests: `pytest tests/ -q` (~2 min; real `ast-grep`/`semgrep` subprocess
  integration tests, not just unit tests).
- End-to-end deterministic run (the CI smoke test):
  `doc-engine pipeline run scripts/fixtures/spring_signals --out-dir <dir> --compliance-profile deterministic_only --skip-drift`,
  then `python3 -m doc_engine.tools.validate_artifacts --all <dir>`.
- Full CI gate list is in `.github/workflows/ci.yml` (`check_repo_claims.py`,
  `rule_coverage.py`, `semgrep_rule_coverage.py`, etc.). Per `CLAUDE.md`, run
  `python3 scripts/ci/check_repo_claims.py` before your final commit in any
  session that touches `scripts/`, `agents/`, or `skills/`.

### Non-obvious gotchas

- `doc-engine certification verify <cert>` **exits non-zero on a
  `deterministic_only` run** because `generative_executor="none"`. This is
  expected — pass `--allow-mock` to verify mock/deterministic certificates. CI
  only checks that `certification.json` exists (`certified: true`), it does not
  call `certification verify`. A live generative run (Claude Code adapter) is
  the only path that writes `generative_executor="live"`.
- The live generative stages (Stages 1–4) need the optional **Claude Code**
  runtime and are not exercisable from a plain Python process. Deterministic
  Stage 0 plus all gates run fully offline with no LLM/network, so that is the
  end-to-end path to use for verification here.
- A shell guard in this environment **blocks piping build/test output into
  `tail`/`head`/`grep`** (because `tail` exits 0 and masks a real test failure).
  Redirect to a file and check the tool's own exit code instead, e.g.
  `pytest tests/ -q > log.txt 2>&1; RC=$?; tail -n 40 log.txt`.
