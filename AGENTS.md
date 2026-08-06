# AGENTS.md

For repo working conventions (steering prompts, session log, `ast-grep`-only
search mandate, state-claim gates), read `CLAUDE.md` first — it is the source of
truth and applies to every session. This file is a thin Cursor Cloud ingest
layer (gotchas + pointers), not a second SoT for recipes or counts.

## Cursor Cloud specific instructions

This is a **Python 3.10+ CLI/SDK** (`doc-engine`). There is no web server or
database. Optional tools (`semgrep`, CodeQL, `gh`) may still touch the network;
do not treat “no app server” as “fully offline / no egress.” Standard
install/lint/test/run commands live in `README.md` and
`.github/workflows/ci.yml`; prefer those over duplicating them here.

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

- Lint / tests / E2E smoke: follow `.github/workflows/ci.yml` and `README.md`
  (do not hardcode suite counts here).
- Before a final commit that touches `scripts/`, `agents/`, or `skills/`, run
  `python3 scripts/ci/check_repo_claims.py` (see `CLAUDE.md`).
- If GitHub Actions is down: `python3 scripts/ci/pre_pr.py --actions-outage`
  (runbook in `scripts/README.md` — do not invent a second local-CI SoT).

### Non-obvious gotchas

- `doc-engine certification verify <cert>` **rejects**
  `generative_executor` of `none` or `mock` unless you pass `--allow-mock`.
  A `deterministic_only` local run typically stamps `none`/`mock` and can still
  write `certified: true` — verify fails without `--allow-mock`. Main
  `.github/workflows/ci.yml` smoke only checks that `certification.json`
  **exists** after the pipeline (it does not read `certified` or call verify).
  The separate `.github/workflows/doc-engine.yml` certification jobs **do** run
  `doc-engine certification verify --allow-mock`.
- `generative_executor="live"` is written by `doc-engine pipeline gates`
  (`live_gates.py`) for any agent that produced docs and then ran gates — not
  only the Claude Code adapter. Live generative *stages* (1–4) still need an
  LLM runtime; deterministic Stage 0 + gates do not need an LLM.
- Pipe-exit pitfall: piping build/test output into `tail`/`head`/`grep` can
  mask a non-zero tool exit (`tail` exits 0). Claude Code sessions have a
  `PreToolUse` hook that blocks that pattern; Cursor Cloud shells may not.
  Always redirect to a file and check the tool’s own exit code, e.g.
  `pytest tests/ -q > log.txt 2>&1; RC=$?; tail -n 40 log.txt` (see
  `claude/tool-quirks.md`).
