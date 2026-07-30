# tests/ — suite taxonomy

Pytest collects recursively under `testpaths = ["tests"]` (see
`pyproject.toml`). Meta tooling discovers the same files via
`scripts/ci/suite_layout.suite_paths` (`rglob`), so nesting is required
layout, not optional packaging.

| Directory | Owns |
|-----------|------|
| `ci/` | Gates and meta contracts: `check_*`, `pre_pr`, `suite_layout`, `prompt_contracts`, `run_manifest`, `control_wiring` |
| `ratchets/` | Mutation / delta / AST-signature / metamorphic / drift-normalization |
| `coverage/` | `rule_coverage`, `semgrep_rule_coverage` |
| `doc_engine/` | Product pipeline, scan, artifacts, Stage-0, partition, certification |
| `adapters/` | Claude hooks: deny_*, require_hardened, adapter_layout, check_pipe_exit_code |

Root keeps `conftest.py` (shared `sys.path` for `scripts/{ci,ratchets,coverage,fixtures}`) and `__init__.py`.

```bash
pytest tests/ -q
pytest tests/ci/test_pre_pr.py -v
pytest tests/doc_engine/test_spring_signal_scan.py -v
```

Inventory without hardcoding a count: `python -c "from pathlib import Path; print(*(sorted(Path('tests').rglob('test_*.py')), sep='\n'))"`.
