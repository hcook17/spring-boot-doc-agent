# Wave 1.5 — CodeQL refuse + cache + merge + containment + stage-boundary bite

**Date:** 2026-08-06  
**Branch:** `wave1-gates-untrusted-tree-hygiene`  
**Status:** implemented (landing on `wave1-gates-untrusted-tree-hygiene`)

## Intent

Wave 1’s build-command allowlist was correctly framed as **foot-gun hygiene**, not an untrusted-tree control. Wave 1.5 makes the real control bite: refuse CodeQL build mode unless `--allow-codeql-build`, harden the results cache, fix merge order, extend walk containment, and close stage-boundary gaps the ETL adversarial suite already named.

## What shipped

| Item | Control |
|------|---------|
| CodeQL build | `CodeQLBuildPolicy` + `--allow-codeql-build`; default REFUSED |
| Allowlist | Drop cmd/ps wrappers; reject `-I`/`-s`/`--init-script`/… |
| Cache | User cache `0700`, CLI version in key, refuse symlink hijack, shape-gate cached rows |
| Merge | Evidence merged before `entity_table_map` derivation; `_merge_entity_table_map` used; `_LOG` not `print` |
| N3 | `partition_repo.dfs_file_list` containment + no dir-symlink follow; config path containment already in loader |
| C2 | `_validate_outputs` reverse `ARTIFACT_FILENAMES`; capacity/facts/covering/edges declared |
| H3 | Failed `end-stage` fails the stage |
| Gap probe | Required deterministic stage after `signal_scan`; `require_gap_probe_artifact` on `validate --all` |
| Stage-0 siblings | `require_stage0_siblings` (facts + covering_proof) |
| Docs | `docs/product-architecture.md` states refuse + allowlist framing |

## Tests that bite

- `test_build_command.py` — pipe-free curl; `-I`/`-s` rejection
- `test_repo_trust.py` — `extra={}` cleared; CodeQL PermissionError
- `test_merge_entity_map_order.py` — evidence-before-map
- `test_codeql_cache_hygiene.py` — XDG cache + symlink refuse + CLI version key
- `test_walk_containment.py` — partition symlink skip
- `test_pipeline_runner.py` — end-stage failure
- `test_etl_adversarial.py` — siblings + gap_report verified gate

## Still open (not this wave)

- Process-group kill on CodeQL timeout
- Full unsigned-cert / atomic-write / N4–N8 backlog from meta-review
