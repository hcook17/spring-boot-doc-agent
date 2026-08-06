# scripts/ — meta CI and fixtures (not the product)

Product Stage-0 / pipeline tools live under `src/doc_engine/` and are invoked as
`python -m doc_engine.tools.<mod>` or `doc-engine`. **Do not re-add product CLIs
here** (STATUS dual-home lock).

This tree is repo meta only:

| Directory | Owns |
|-----------|------|
| `ci/` | Gate checkers: `check_repo_claims`, `check_code_quality`, `check_llms_coverage`, `check_workflow_yaml`, `check_no_client_identifiers`, `pre_pr`, `setup_codeql.sh`, plus `suite_layout`, `prompt_contracts` |
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

python3 scripts/ci/pre_pr.py --auto            # default from .githooks/pre-push
python3 scripts/ci/pre_pr.py --fast            # tier 0 + claims
python3 scripts/ci/pre_pr.py --full            # + Stage-0 + advisory mutate/metrics
python3 scripts/ci/pre_pr.py --actions-outage  # CI parity when Actions is down
```

| Mode | Hard suites |
|------|-------------|
| `--fast` | workflow YAML (+ security severity ramp), tool-doctor, ruff, repo_claims |
| `--auto` / default | docs-only → fast; otherwise **standard** CI hard tiers (quality, coverage, pytest) |
| `--full` | all hard + portable Stage-0 + advisory mutate/metrics (+ mutation_driver when present) |
| `--actions-outage` | `--full` + CodeQL invariants/compile/QL tests/fixture runtime + `certification verify --allow-mock` (scan_only + certified) |

Receipt: `.git/pre-pr-receipt.json` (schema 2: optional `attestation` /
`github_status_note` for outage mode). Bypass (logged): `PRE_PR_SKIP=1` **and**
`PRE_PR_SKIP_REASON='…'` (≥8 chars) → `.git/pre-pr-bypass.log`. Bypass is
**refused** under `--actions-outage`.

`check_workflow_yaml.py` hard-fails critical/high Actions footguns (script
injection, write-all, missing permissions, third-party unpinned tags);
`actions/*@vN` stays **advisory** until a SHA-pin PR.

### Actions outage (local CI parity)

When GitHub Actions is down (action download 503s, jobs stuck queued — see
https://www.githubstatus.com Actions component), run hermetic CI parity locally
instead of waiting on the second line:

1. Confirm the outage on GitHub Status (Actions = major/partial outage).
2. Activate the venv. Ensure **Java 17+** and **bash** (Git Bash on Windows).
3. Bootstrap the pinned CodeQL CLI if needed (same digest as `ci.yml`):
   ```bash
   bash scripts/ci/setup_codeql.sh
   eval "$(bash scripts/ci/setup_codeql.sh --print-path-export)"
   ```
   Non-linux64: set `CODEQL_BUNDLE_URL` + `CODEQL_SHA256` from the matching
   codeql-action release asset, or put an existing `codeql` v2.26.2 on `PATH`.
4. Run:
   ```bash
   python3 scripts/ci/pre_pr.py --actions-outage --status-url 'https://www.githubstatus.com/'
   ```
5. On overall pass, keep `.git/pre-pr-receipt.json` (`attestation: actions_outage`)
   with the push/PR; cite `git_sha` in the PR comment.
6. When Actions recovers, re-run CI on the same SHA — the receipt is interim
   attestation, not a permanent substitute for the merge-time second line.

**Non-goals for outage mode:** Pages deploy, Artifactory ocs databases,
`pr-comment`, and anything that would revive `verify_llms_docs.py`.

## Invoke examples

```bash
python3 scripts/ci/check_repo_claims.py
python3 scripts/ci/check_code_quality.py
python3 scripts/ci/pre_pr.py --fast
bash scripts/ci/setup_codeql.sh   # optional; needed for --actions-outage
python3 scripts/coverage/rule_coverage.py
python3 scripts/ratchets/mutate.py
```

Baselines for the CI checkers live in `ratchets/`; coverage baselines stay beside the coverage runners. Path helpers: `doc_engine.paths.scripts_dir()` / `scripts_meta_path_entries()`.

Suites mirror this taxonomy under [`tests/`](../tests/README.md) (`ci/`, `ratchets/`, `coverage/`, `doc_engine/`, `adapters/`). Discovery is recursive via `suite_layout.suite_paths`.
