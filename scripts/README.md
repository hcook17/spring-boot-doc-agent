# scripts/ — meta CI and fixtures (not the product)

Product Stage-0 / pipeline tools live under `src/doc_engine/` and are invoked as
`python -m doc_engine.tools.<mod>` or `doc-engine`. **Do not re-add product CLIs
here** (STATUS dual-home lock).

This tree is repo meta only:

| Directory | Owns |
|-----------|------|
| `ci/` | Gate checkers: `check_repo_claims`, `check_code_quality`, `check_llms_coverage`, `check_workflow_yaml`, `check_no_client_identifiers`, `pre_pr`, plus `suite_layout`, `prompt_contracts` |
| `ratchets/` | Mutation harness (`mutate`, `set_delta`, perturbations, AST signatures) and committed baselines (`*_baseline.json`) |
| `coverage/` | Rule non-vacuity / backtest: `rule_coverage`, `semgrep_rule_coverage`, fixtures, `spring_semgrep_rules.yml` |
| `schemas/` | JSON Schema exports derived from `doc_engine.pipeline.artifacts` (+ `run_manifest.schema.json`) |
| `fixtures/` | Stage-0 spring_signals fixture tree + snapshot JSON + regenerate/oracle helpers |

## Principal-engineer pre-PR gate

Local fail-closed orchestrator (CI remains merge-time second line). Git cannot
intercept `gh pr create`; push is the choke point.

```bash
# one-time per clone
git config core.hooksPath .githooks

python3 scripts/ci/pre_pr.py --auto   # default from .githooks/pre-push
python3 scripts/ci/pre_pr.py --fast   # tier 0 + claims
python3 scripts/ci/pre_pr.py --full   # + Stage-0 + advisory mutate/metrics
```

| Mode | Hard suites |
|------|-------------|
| `--fast` | workflow YAML (+ security severity ramp), tool-doctor, ruff, repo_claims |
| `--auto` / default | docs-only → fast; otherwise **standard** CI hard tiers (quality, coverage, pytest) |
| `--full` | all hard + portable Stage-0 + advisory mutate/metrics |

Receipt: `.git/pre-pr-receipt.json`. Bypass (logged): `PRE_PR_SKIP=1` **and**
`PRE_PR_SKIP_REASON='…'` (≥8 chars) → `.git/pre-pr-bypass.log`.

`check_workflow_yaml.py` hard-fails critical/high Actions footguns (script
injection, write-all, missing permissions, third-party unpinned tags);
`actions/*@vN` stays **advisory** until a SHA-pin PR.

## Invoke examples

```bash
python3 scripts/ci/check_repo_claims.py
python3 scripts/ci/check_code_quality.py
python3 scripts/ci/pre_pr.py --fast
python3 scripts/coverage/rule_coverage.py
python3 scripts/ratchets/mutate.py
```

Baselines for the CI checkers live in `ratchets/`; coverage baselines stay beside the coverage runners. Path helpers: `doc_engine.paths.scripts_dir()` / `scripts_meta_path_entries()`.

Suites mirror this taxonomy under [`tests/`](../tests/README.md) (`ci/`, `ratchets/`, `coverage/`, `doc_engine/`, `adapters/`). Discovery is recursive via `suite_layout.suite_paths`.
