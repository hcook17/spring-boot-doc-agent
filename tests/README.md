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

### Platform-boundary oracles (`doc_engine/` scanners)

When touching `src/doc_engine/scanning/_scanner_*.py`, argv builders, `ScanContext`, or `_PATH_LIST_*` / `sys.platform` branches, update [`tests/doc_engine/test_scan_context_wiring.py`](doc_engine/test_scan_context_wiring.py). The oracle is the **ScanContext inventory invariant**, not “ast-grep exited 0”:

- With `java_files` supplied: never fall back to a bare repo-root argv; chunk/bisect under budget pressure.
- Assert the batching warning (`preserve ScanContext inventory`); tombstone `scanning repo root instead`.
- Equivalence: unlimited budget (one call) vs tiny budget (N calls) → same concatenated match list.
- Injectable `_PATH_LIST_CHAR_LIMIT` + raised `OSError(winerror=206)` keep these non-vacuous on Linux CI; `java_files is None` remains the only intentional root-scan path.
- Mechanical twin: `behavior:astgrep_inventory_never_widens_to_repo_root` in `scripts/ci/check_repo_claims.py` (see `CONSTRAINTS.md` Known precision item 14).

```bash
pytest tests/ -q
pytest tests/ci/test_pre_pr.py -v
pytest tests/doc_engine/test_spring_signal_scan.py -v
pytest tests/doc_engine/test_scan_context_wiring.py -v
```

Inventory without hardcoding a count: `python -c "from pathlib import Path; print(*(sorted(Path('tests').rglob('test_*.py')), sep='\n'))"`.
