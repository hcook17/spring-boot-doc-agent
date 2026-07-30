# scripts/ — meta CI and fixtures (not the product)

Product Stage-0 / pipeline tools live under `src/doc_engine/` and are invoked as
`python -m doc_engine.tools.<mod>` or `doc-engine`. **Do not re-add product CLIs
here** (STATUS dual-home lock).

This tree is repo meta only:

| Directory | Owns |
|-----------|------|
| `ci/` | Gate checkers: `check_repo_claims`, `check_code_quality`, `check_llms_coverage`, `check_workflow_yaml`, `check_no_client_identifiers`, plus `suite_layout`, `prompt_contracts` |
| `ratchets/` | Mutation harness (`mutate`, `set_delta`, perturbations, AST signatures) and committed baselines (`*_baseline.json`) |
| `coverage/` | Rule non-vacuity / backtest: `rule_coverage`, `semgrep_rule_coverage`, fixtures, `spring_semgrep_rules.yml` |
| `schemas/` | JSON Schema exports derived from `doc_engine.pipeline.artifacts` (+ `run_manifest.schema.json`) |
| `fixtures/` | Stage-0 spring_signals fixture tree + snapshot JSON + regenerate/oracle helpers |

## Invoke examples

```bash
python3 scripts/ci/check_repo_claims.py
python3 scripts/ci/check_code_quality.py
python3 scripts/coverage/rule_coverage.py
python3 scripts/ratchets/mutate.py
```

Baselines for the CI checkers live in `ratchets/`; coverage baselines stay beside the coverage runners. Path helpers: `doc_engine.paths.scripts_dir()` / `scripts_meta_path_entries()`.
