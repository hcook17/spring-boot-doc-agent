# Constraints

Current-state catalog of real constraints **doc-engine** and this monorepo operate under. Correct in place (`CLAUDE.md`); this is not an append-only log. Written for `claude/steering-prompts/03-constraints-research-prompt.md`; cross-linked from `README.md` and `skills/document-spring-repo/SKILL.md`. Product layout: [`docs/product-architecture.md`](docs/product-architecture.md).

Entry shape: **status + one current fact + residual if any.** Diary / addenda belong in `claude/session-log.md` or research memos, not here. Bracket status tags must close before the lead sentence (the form check B parses).

Kinds: Runtime prerequisites · Integration gaps · Known precision tradeoffs · Confidentiality/handling · Enterprise-readiness gaps.

---

## Runtime prerequisites

1. **Standing** — `ast-grep` on `PATH` is a hard dependency for default Stage 0 (`filesystem` + `ast-grep`; `resolve_scanner_names`). Install via `requirements.txt` (`ast-grep-cli~=0.45.0`). CodeQL is opt-in (`--scanners filesystem,codeql`); missing CodeQL on that path raises `CodeQLNotFoundError` / exits 1. Default scans and `capacity_preflight` do **not** require CodeQL. Residual: `cargo`/`npm` installs can PATH-shadow the pin — see `claude/tool-quirks.md`.

2. **Standing** — SQLLineage (`sqllineage~=1.5.8` in `requirements.txt`) is soft at scan runtime (lineage field degrades without it) but **hard for the test suite**: missing install fails lineage assertions in `tests/doc_engine/test_spring_signal_scan.py`.

3. **Standing** — `pathspec` (`pathspec~=1.1.1`) is soft; only used when `--respect-gitignore` is passed. Missing install disables that flag's Python matching; default (flag omitted) is unaffected.

4. **[Resolved]** Python runtime deps are pinned in root `requirements.txt` (`ast-grep-cli`, `sqllineage`, `pathspec`, `semgrep`); CI installs via `pip install -r requirements.txt`. CodeQL CLI is intentionally absent (standalone binary). `requirements-dev.txt` pins `ruff` separately — not merged into runtime. Residual: none for pinning itself; CodeQL remains opt-in. <!-- verify: path_exists:requirements.txt; contains:requirements.txt:ast-grep-cli; contains:requirements.txt:sqllineage; path_exists:requirements-dev.txt; contains:.github/workflows/ci.yml:requirements.txt -->

5. **Standing** — `semgrep` on `PATH` (`semgrep~=1.171.0`) is required for `software-architect-and-testing` ruleset / `semgrep_rule_coverage.py`, **not** Stage 0. Missing binary → coverage script exits 2; binary-dependent tests `skipTest`. CI also runs hermetic FP ratchet vs negative fixtures. Residual: optional real-corpus recall baseline file remains absent (do not invent a client checkout name). Quirk: local-path config prefixes `check_id`; `_normalize_check_id()` takes the last dotted segment.

## Integration gaps, not scope cuts

1. **Standing** — `spring_drift_check` is real and CI-tested, but not auto-invoked by the pipeline. Documented as optional Stage 0 pre-flight in `SKILL.md` / `README.md`. You run it when you have a prior `spring_signals.json`. For current tests: `pytest tests/doc_engine/test_spring_drift_check.py`.

2. **[Resolved]** CI exists; merges are not gated by it. `.github/workflows/ci.yml` runs on `pull_request`/`push` to `main`: `pytest tests/` (`pyproject.toml` `testpaths`), ruff on `scripts/` + `src/doc_engine/`, `check_code_quality.py` (annotation/docstring hard-fail; size/complexity advisory), `check_repo_claims.py`, coverage gates. Stacked PRs targeting a non-`main` base get **no** CI (filter is intentional). Residual: no branch-protection required checks — Enterprise item 3 below. Closes `07-ci-scaffold-task-prompt.md` for wiring, not for merge policy. <!-- verify: path_exists:.github/workflows/ci.yml; contains:.github/workflows/ci.yml:check_repo_claims.py; contains:.github/workflows/ci.yml:pytest -->

3. **[Resolved]** Run-level telemetry exists. `src/doc_engine/tools/run_manifest.py` writes `run_manifest.json` (CLI `init`/`start-stage`/`end-stage`/`finalize`/`summary` from `SKILL.md`). `finalize` marks stuck stages `canceled` / run `partial`; if the session dies before `finalize`, status stays `"running"` forever. Optional `--manifest` feeds `file_signatures` into `spring_drift_check` as tier-1 baseline. Residual: not CI-triggered; not yet proven on a non-fixture target-repo run. <!-- verify: path_exists:src/doc_engine/tools/run_manifest.py; contains:src/doc_engine/tools/spring_drift_check.py:--manifest -->

4. **[Flagged, not yet resolved]** Do not revive `scripts/verify_llms_docs.py`. Deleted as an RCE defect (`bash -c` over LLM markdown with `GH_TOKEN`). Intent remains: readers re-run pinned commands deliberately from a trusted checkout. Completeness half is `scripts/ci/check_llms_coverage.py` — **always advisory** (exit 0); hard gate needs a redesigned exemption, not an `ENFORCE` flip. Residual: exemption heuristic (“most-recently-merged PR”) is provisional; semantic match of command *output* to `Expect:` prose was never automated. See `STATUS.md` Pending. <!-- verify: path_absent:scripts/verify_llms_docs.py -->

## Known precision tradeoffs

1. **Standing** — Source-text (ast-grep) vs bytecode/ArchUnit trades inherited/meta-annotation and indirect-interface precision for no build/classpath. Documented in `README.md`.

2. **[Resolved]** JPQL lineage for the single-entity no-join case only. <!-- verify: contains:src/doc_engine/scanning/_merge_signals.py:"contested"; contains:src/doc_engine/scanning/_resolve_lineage.py:ambiguous simple name across packages; contains:tests/doc_engine/test_spring_signal_scan.py:test_duplicate_class_name_is_contested_with_lowest_path_identity; contains:tests/doc_engine/test_spring_signal_scan.py:test_contested_entity_name_refuses_lineage; contains:src/doc_engine/scanning/symbol.py:SYMBOL_GRAMMAR_VERSION; contains:claude/research/claim-symbol-grammar-2026-07-30.md:doc-engine spring --> `resolve_jpql_to_lineage()` rewrites via `entity_table_map`. Out of scope (honest `available: false`): multi-entity/joins, association paths, JPQL-only functions, `@Entity(name=...)` overrides, polymorphic `FROM`, embeddable/composite key paths. **Contested simple names:** map keeps lowest-path citation identity + `status: "contested"` / `candidates`; lineage refuses. Facts SoR uses distinct claim-symbols; Path A map stays simple-name-keyed. Winner `table` on contested entries is citation identity only. JPQL drift uses multi-file provenance (`resolved_via_entity` + `_reverify_jpql_lineage_provenance`).

3. **[Partially resolved]** Cross-group relationships have stated limits. <!-- verify: path_exists:src/doc_engine/tools/build_cross_group_edges.py; contains:src/doc_engine/tools/build_cross_group_edges.py:same_package_outside --> Same-package split across groups is now explicit (`same_package_outside` via `build_cross_group_edges.py`). Residuals: wildcard imports → `package-fanout`; interface-mediated DI not recoverable from import graph alone.

4. **Standing** — No published precedent for this drift-check design (tier-1 hashes; tier-2 one fresh scan + per-citation compare). Deliberate departure from LLM trace-link literature (arXiv:2506.16440). Indirect justification only.

5. **[Resolved]** Scan output byte-determinism is an asserted invariant. `entity_table_map` is sorted on emit and pinned by tests. Residual: re-run-and-diff inside one process can miss order bugs — prefer naming the invariant. <!-- verify: contains:tests/doc_engine/test_spring_signal_scan.py:entity_table_map -->

6. **[Resolved]** Partition overlap does not cascade across >2 groups. <!-- verify: contains:src/doc_engine/tools/partition_repo.py:carried_in_paths; contains:src/doc_engine/tools/partition_repo.py:via overlap from the prior group are not re-carried; contains:tests/doc_engine/test_enterprise_kitchen_sink.py:test_overlap_never_spans_more_than_two_groups; contains:tests/doc_engine/test_enterprise_kitchen_sink.py:test_overlap_is_adjacent_only; not_contains:tests/doc_engine/test_enterprise_kitchen_sink.py:@unittest.expectedFailure --> `carry_forward(..., carried_in_paths=...)` skips prior-overlap seeds. Pinned on kitchen-sink + opt-in mid-size lane.

7. **[Resolved]** Multi-segment Spring profile names are recognized as configuration. <!-- verify: contains:src/doc_engine/scanning/_scanner_filesystem.py:application(-[\w.-]+); contains:tests/doc_engine/test_enterprise_kitchen_sink.py:test_multi_segment_profile_names_are_recognized_as_config; contains:tests/doc_engine/test_enterprise_kitchen_sink.py:MULTI_SEG_YML --> `CONFIG_NAME_PATTERNS` matches `application-dev-local.yml`-style names.

8. **[Flagged, not yet resolved]** Write-scope gate is blind to gitignored paths. `check_pipeline_output.py` uses `git status --porcelain`, so writes into `target/` / `build/` / other ignored dirs pass silently. Pinned in `Ch12GateResponsibilityTest`. <!-- verify: contains:src/doc_engine/tools/check_pipeline_output.py:status", "--porcelain; contains:src/doc_engine/tools/check_pipeline_output.py:Ignored untracked paths -->

9. **[Flagged, not yet resolved]** Tier-2 first-line match identity false-positives on wrapped annotations. `first_line_match()` truncates multi-line matches; measured 2/208 FPs on formatting-only fixture perturbations (`api_surface__mapping`). Fixing means separating compare-identity from stored `match` schema — own decision. Candidate normalizers: `pytest tests/ratchets/test_drift_normalization.py`. <!-- verify: contains:src/doc_engine/scanning/java_extract.py:def first_line_match; path_exists:tests/ratchets/test_drift_normalization.py -->

10. **[Resolved]** Rules must prove they can fire; silent zero ≠ absent. <!-- verify: path_exists:scripts/coverage/rule_coverage.py; path_exists:scripts/fixtures/spring_signals; path_exists:scripts/coverage/rule_fixtures; contains:.github/workflows/ci.yml:rule_coverage.py; not_contains:adapters/claude/agents/doc-writer.md:Grep --> `rule_coverage.py` fails CI if a pack `rule_id` hits nothing under `scripts/fixtures/spring_signals/`. Metamorphic corpus is `rule_fixtures/`. Agents barred from text search (check F + `deny_text_search.py`). Residual: fixtures prove *can* fire, not *correct* fire; `@Name` vs `@Name($$$)` shapes are disjoint; ast-grep exit 0 on zero matches means unproven.

11. **[Partially resolved]** Build scripts emit heuristic deployment signals; Groovy is not structurally parseable. <!-- verify: path_exists:src/doc_engine/scanning/support/_build_signal_extract.py; contains:src/doc_engine/scanning/_scanner_filesystem.py:extract_build_signals; contains:tests/doc_engine/test_build_signal_extract.py:deployment__build_plugin; contains:tests/doc_engine/test_enterprise_kitchen_sink.py:test_build_gradle_signals_extracted; contains:src/doc_engine/tools/spring_drift_check.py:_recheck_build_signals --> `ast-grep -l groovy` fails; `_build_signal_extract.py` emits typed `deployment__build_*` rows. Out of scope: dynamic Groovy, full task graph, BOM expansion beyond literals. Drift rechecks via `_recheck_build_signals()`. Placeholder values are unquoted before secret heuristics (`password="${X}"`).

12. **[Flagged, not yet resolved]** External-research citations are never mechanically re-verified. arXiv / GitHub / deepwiki ids in `architecture_testing_review.json` are recorded once with no offline re-resolve. Permanent: local CI checkers must not take a live network dependency. Deleted / refuse revival of any live-fetch external-research re-verifier under scripts/ci. <!-- verify: contains:adapters/claude/agents/software-architect-and-testing.md:External research; path_absent:scripts/ci/verify_external_research.py -->

13. **[Resolved]** Entity recall requires an independent oracle arm; default Stage 0 must not claim it. With CodeQL (or future multipass/metamodel) in `--scanners`, Stage 0 writes `RECALL_MISS` facts; `gap_probe` scores `R_recall` only when that arm is present. Residual: EVIDENTIARY misses stay typed; multipass not a registered scanner. See `claude/research/stage0-covering-absence-recall-2026-07-30.md`. <!-- verify: contains:src/doc_engine/scanning/recall_delta.py:RECALL_MISS; path_exists:claude/research/stage0-covering-absence-recall-2026-07-30.md -->

14. **[Resolved]** ScanContext inventory must not widen to repo-root ast-grep under argv pressure. <!-- verify: behavior:astgrep_inventory_never_widens_to_repo_root; contains:src/doc_engine/scanning/_scanner_astgrep.py:_invoke_ast_grep_chunked; contains:src/doc_engine/scanning/_scanner_astgrep.py:chunk_paths_for_argv; not_contains:src/doc_engine/scanning/_scanner_astgrep.py:scanning repo root instead; contains:tests/doc_engine/test_scan_context_wiring.py:preserve ScanContext inventory --> Chunk/bisect only; `java_files is None` fails closed. Covering receipts required for green Path A. Residual: no `windows-latest` CreateProcess witness job yet.

15. **[Resolved]** Empty evidence ≠ feature absent; absence is decidable only inside callable trials. <!-- verify: contains:src/doc_engine/scanning/absence.py:ABSENCE; contains:src/doc_engine/scanning/covering.py:covering_proof; contains:src/doc_engine/scanning/gap_probe/common.py:CoveringPreconditionError; path_exists:scripts/schemas/covering_proof.schema.json; path_exists:claude/research/stage0-covering-absence-recall-2026-07-30.md --> Writers emit `ABSENCE` or `UNPROVEN`; `gap_probe` refuses S2 without covering; `U_w` is not completeness. Residual: EVIDENTIARY misses and non-callable UNPROVEN remain explicit.

## Confidentiality/handling rules

1. **Standing rule** — when run against a real target repo, that repo's real name and any excerpt of its source/config/generated docs must not land in this plugin's **tracked** files (prose, `.gitignore`, workflow YAML, fixtures, Makefiles — every carrier). Use synthetic / already-public names. Machine-specific ignores go in `.git/info/exclude`. Residual: `check_no_client_identifiers.py` covers aggregate-JSON bytecode-oracle carriers, not every config leak — convention still primary.

2. **[Resolved]** Secret leakage into generated docs is mitigated heuristically, not guaranteed. Scan records `redaction_zones` (never values); agents instructed not to transcribe flagged lines; `check_no_secrets_leaked.py` re-applies heuristics to run output (optional post-run, not CI-wired). Config reads use `utf-8-sig`. Complementary: `config_key_sets` + drift statuses distinguish structure vs values-only changes. Residual: unrecognized key names / free-text secrets outside key-agnostic patterns. <!-- verify: path_exists:src/doc_engine/scanning/support/_secret_heuristics.py; path_exists:src/doc_engine/tools/check_no_secrets_leaked.py -->

3. **Standing rule** — external research must not send target-repo identifiers outbound. Frame queries around general tech/patterns, never real class/table/business names or `redaction_zones` contents. Enforcement: agent prompt discipline + Bash raw-network deny (`deny_raw_network.py` + check F). Residual: content of `WebFetch` queries is not mechanically checked against an identifier list.

## Enterprise-readiness gaps

Audit posture for use beyond a single operator. Pointer-only “see Runtime/Integration item N” duplicates (license, pinning, “see telemetry above”) are omitted — those entries remain above.

1. **Standing** — No RBAC or auth layer. Gated only by the operator's Claude Code / filesystem / LLM access. (`@PreAuthorize` extraction and `authorization.md` are about the *target* repo.)

2. **Standing** — No multi-repo or batch story. One `<repo_path>` per invocation; no aggregate-across-services mechanism.

3. **[Partially resolved]** PRs land with zero required status checks / reviews. CI exists (Integration item 2); branch protection does not — `gh api .../branches/main/protection` was 404 as of 2026-07-30. Deliberately owner-deferred (admin blast radius). When resumed: require `test` context + ≥1 review via the `gh api` PUT documented historically in session log / prior revisions of this file. Today's substitute is single-operator write-then-verify (`CONTRIBUTING.md` / `claude/llms/`); that does not replace protection once this is a team project. <!-- verify: path_exists:.github/workflows/ci.yml; contains:STATUS.md:L4; contains:STATUS.md:branch protection -->

**Close-out order for enterprise rollout:** confidentiality/secret-redaction → branch protection + required reviews → audit trail depth / run-manifest adoption → RBAC / multi-repo (lowest urgency). License (`MIT` in `.claude-plugin/plugin.json`) and dependency pinning (`requirements.txt`) are done — see Runtime item 4. Full scorecard: `MATURITY_ASSESSMENT.md`.

Related tools (neither closes an open item above by itself): `skills/semantic-pipeline-eval/`, `skills/capacity-preflight/` (`capacity_preflight.py` measures per-group `cross_group_edges` slices — not the retired Stage-1 broadcast).
