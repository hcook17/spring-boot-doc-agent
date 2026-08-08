# Testing doctrine (principal-engineer bar)

This repo uses a **dual-lane** gate: GitHub Actions stays hermetic (no client
checkouts); merge readiness for Stage-0 work also requires a **real Spring
tree** via `DOC_ENGINE_REAL_REPO`. See [`tests/README.md`](README.md) for suite
layout.

## Taxonomy

| Layer | Purpose | Synthetics allowed? |
|-------|---------|---------------------|
| Unit falsifiers | Prove a formula/branch bites | Minimal hand dicts OK if each case names the axiom it falsifies |
| Contract / schema | Round-trip + closed vocabulary | Hand JSON OK; must share SoT with `scripts/schemas/` |
| Integration | Real tools on a tree | Prefer real/fixture scan; never mock `ast-grep`/`semgrep` *output* as product truth |
| Metamorphic / ratchet | Known input deltas → known output deltas | Controlled corpora OK (`scripts/coverage/rule_fixtures/`) |
| Real-repo (canonical) | Ambiguity killer on production-scale distributions | **Required** via `DOC_ENGINE_REAL_REPO` when Stage-0 paths change (`pre_pr` real_repo lane) |
| E2E / kitchen-sink | Hostile encoding + subprocess exit codes | Synthetic **hostile** repo OK (adversarial, not a stand-in for product truth) |
| Generative / LLM | Semantic quality | Mechanical shape in CI; live/semantic eval stays explicit opt-in |

## TDD for Stage-0

1. Write or extend a failing **real-repo** or **scan-derived** test first.
2. Implement until it passes.
3. If anonymized external-corpus bands move intentionally, regenerate
   `scripts/coverage/real_repo_gap_baseline.json` in the same change and explain why.

Hand-built full graphs are axiom falsifiers only — they are not proof that a
mid-size service still measures healthy rates.

## Canonical real fixture

```bash
# Point at any local Spring Boot tree (never commit the path or client name).
export DOC_ENGINE_REAL_REPO=/path/to/local-spring-tree

# Or write one absolute path line to the gitignored pointer file:
#   local-runs/real-repo.path
# Env vars still win over the file when both are set.

# Optional fast artifact lane (gitignored):
python scripts/ci/regen_real_repo_artifacts.py
export DOC_ENGINE_REAL_ARTIFACTS_DIR=local-runs/real-repo-latest
```

Legacy aliases (still honored when the canonical vars are unset):

- `GAP_PROBE_OCS_REPO` / `GAP_PROBE_OCS_ARTIFACTS_DIR` / `GAP_PROBE_OCS_LIVE_SCAN`
- `DRIFT_OCS_REPO` / `DRIFT_OCS_ARTIFACTS_DIR` / `DRIFT_OCS_LIVE_SCAN`
- `PARTITION_REPO_REAL_FIXTURE_DIR` / `KITCHEN_SINK_REPO`

Resolver: `doc_engine.real_fixture` (env → legacy aliases → `local-runs/real-repo.path`).

Product-truth ETL / gap / drift / partition real-world suites **require** this
lane — they no longer scan the hermetic `scripts/fixtures/spring_signals`
tree as a stand-in for a mid-size Spring service.

## What never certifies doc quality

- `MockStageExecutor` / `generative_executor: mock` — structural wiring only.
  Under the `certified` profile, `certification.json` stays `certified: false`
  unless `--allow-mock` / `allow_mock=True` is explicit (builder + verify).
- Synthetic agent-shaped JSON in `test_pipeline_stages.py` — tag/citation/shape
  contracts, not truthfulness.
- Kitchen-sink — proves CLI exit codes and hostile I/O, not semantic docs.
- `covering_ok=True` without a covering proof — rate math only; `s1_covering.verified`
  must stay false (see `tests/doc_engine/test_real_fixture_adversarial.py`).
- Silent omit of `R_recall` / oracle — gap reports always stamp
  `oracle.claim` (`measured` | `omitted_without_oracle` | `untrusted_planted`);
  never invent RECALL_MISS; planted misses without CodeQL → `untrusted_planted`.
- `validate --all` / runner require a **content-bearing** gap_report
  (`s1_covering.verified`, schema), not mere file presence.
- `verify_certification` **refolds** via `build_certification_report` — never
  trusts the stored `certified` bit alone.
- `--signals-file` refuses stub `covering_proof.json` that fails verification.
- scan_only = Path A schema audit only (not Stage-0 complete; no gap_probe / U).

## Adversarial suite

- `tests/doc_engine/test_real_fixture_adversarial.py` — gap/covering/baseline lies
- `tests/doc_engine/test_etl_adversarial.py` — Stage-0 → gates ETL (validate --all,
  gap_probe required after signal_scan, stage outputs, `--signals-file` siblings,
  partition/edges vacuity, tampered covering)

`covering_ok=True` without a covering proof — rate math only; `s1_covering.verified`
must stay false.

Run with your real artifacts when iterating capture:

```bash
DOC_ENGINE_REAL_REPO=/path/to/local-spring-tree \
DOC_ENGINE_REAL_ARTIFACTS_DIR=local-runs/real-repo-latest \
  pytest tests/doc_engine/test_real_fixture_adversarial.py tests/doc_engine/test_etl_adversarial.py -v
```

## Public CI vs merge readiness

| Gate | Proves |
|------|--------|
| `.github/workflows/ci.yml` | Hermetic fixtures, ratchets, anonymized baselines, mechanical contracts |
| `scripts/ci/pre_pr.py` real_repo lane | Live/artifact outcomes on `DOC_ENGINE_REAL_REPO` when Stage-0 paths change |

Confidentiality: do not vendor real target source into `scripts/fixtures/`, and
do not put denylist tokens (see `scripts/ci/client_identifier_denylist.txt`)
into tracked files.
