# Review: Adversarial design-pattern pass — spring-boot-doc-agent (whole tree)

Reviewed: 2026-08-06 · Workspace `C:/Users/16145/Downloads/spring-boot-doc-agent_1/spring-boot-doc-agent`  
Scope: creational / structural / behavioral patterns, SRP, anti-patterns, N+1 / integrity, input validation, architectural documentation.  
**No code was changed in this pass** — findings and remediation waves only.

> **Errata (same day):** An external meta-review corrected several severities and named trust-boundary misses (N1–N4). Authoritative corrected table, H2 covering-proof REFUTED, and revised Wave 1 live in [`design-patterns-meta-review-adjudication-2026-08-06.md`](design-patterns-meta-review-adjudication-2026-08-06.md). Do not implement Wave 1 from §5 below without reading that adjudication (especially: do **not** raise on signature-hash conflict; do treat C1 as High not Critical).

**Methodology:** Principal + mathematician lenses from `claude/steering-prompts/10-review-persona-and-standards.md`; DDIA decision procedure from `docs/design/ddia-north-star/playbooks/architecture-decision-review.md`. Every load-bearing claim below is **CONFIRMED** against Tier A source (file + line), or explicitly scoped. Explore passes that oriented the search were re-verified before inclusion; Tier C subagent output never stands alone as a citation.

Exploration attribution (orientation only until verified):
- [Explore core architecture](52928e24-e3f3-4343-97be-31ebe9f86231)
- [Explore pipeline and scanning](039d8ff6-015d-49d0-9a6c-4373ea948ddd)
- [Explore adapters and CLI](b2309904-f4c6-41f3-be44-cfc4be031b96)
- [Verify N+1 and god modules](8333a41a-bf02-4cf8-aaa0-d276c5bd148e)

---

## 1. Overview

Stage 0 scanning is the strongest architectural surface in the tree: Strategy + registry, covering-proof barrier, shared walk SoR, contested-entity refuse-to-guess, and honest certification folding. Pipeline orchestration and the public SDK façade are weaker: vacuous or half-wired contracts, dual runners, anemic `dict` signals, and a few fail-open merges/validators that contradict their own comments.

Per prompt 10, confidently wrong derived docs / certifications outrank crashes. Several findings below are exactly that class — gates that look like gates, merges that look deterministic, and package docs that oversell language-agnostic / hexagonal depth.

```text
Stage 0 (strong)                         Orchestration (weaker)
SCANNERS / get_scanner                   build_stage_specs (SoT — good)
  → run_scan + covering receipts           → PipelineRunner (partial contracts)
  → merge_signals                          → local_runner.Runner (gates/cert/log)
  → lineage + covering_proof               → Engine.generate_docs (placeholder)
```

---

## 2. What already bites (keep)

| Pattern | Where | Why it works |
|---------|-------|--------------|
| Registry + factory | `src/doc_engine/scanning/_scanner_registry.py` `SCANNERS` / `get_scanner` | Closed set; unknown names raise |
| Protocol + ABC | `src/doc_engine/core/protocols.py`, `scanning/_scanner_base.py` | Structural `Scanner` port; concrete backends |
| Stage-graph SoT + strategy | `pipeline/stages.py` `build_stage_specs`, `runner.py` kind branch | Single executable graph; profiles / `--until` cite it |
| Covering barrier (fail-closed) | `scanning/_orchestrator.py`, `scanning/covering.py` | Missing/incomplete receipt → `CoveringProofError` |
| One-walk inventory SoR | `core/context.py` + `core/walk.py` | Avoids N+1 full-repo walks across scanners |
| Boundary DTOs | `pipeline/artifacts.py` + `pipeline/validation.py` | Pydantic contracts; Fact ledger `extra="forbid"` |
| Build-command metachar deny | `scanning/build_command.py` | Rejects `;|&`$<>` chaining (incomplete — see H1) |
| Cert honesty | `pipeline/compliance.py`, `tools/certification.py` | Mock/live provenance; verify rejects mock unless `--allow-mock` |
| Intent docs | `docs/product-architecture.md`, DDIA north-star, `partition_repo` ArchAgent header | Complex decisions explained *why* |

---

## 3. Specific issues found

### Critical

#### [Critical] C1 — Boundary schema failures escape `PipelineRunner`

**Verdict:** CONFIRMED  
**Anti-pattern:** Gate that is not a gate (prompt 10 §4)  
**DDIA:** `gate-needs-witness`

`PipelineRunner.run` only converts `FileNotFoundError` from `_validate_outputs` into a stage failure:

```44:54:src/doc_engine/pipeline/runner.py
            try:
                self._validate_outputs(spec, context)
            except FileNotFoundError as exc:
                fail = StageResult(
                    success=False,
                    error=str(exc),
                    detail="missing_required_output",
                )
                results[-1] = (spec.name, fail)
                context.log(f"  !! stage {spec.name} failed: {exc}")
                break
```

`_validate_outputs` calls `validate_artifact_file`, which raises `ArtifactValidationError` on schema failure (`validation.py` ~18, ~62–74). That exception is uncaught. A malformed `spring_signals.json` / `groups.json` after a zero-exit subprocess becomes a traceback instead of `StageResult(success=False)` with a cert fold. Existing tests cover missing files, not bad schemas (`test_missing_required_output_is_stage_failure_not_crash`).

**Fix direction:** Catch `ArtifactValidationError` (and `json.JSONDecodeError`) the same way as missing outputs.

---

#### [Critical] C2 — Declared outputs often existence-only; capacity has no outputs

**Verdict:** CONFIRMED  
**Anti-pattern:** Incomplete / illusory validator

`_validate_outputs` schema-validates only filenames in a hard-coded `name_map` (`spring_signals`, `groups`, `summaries`, `interview_answers`). `signal_scan` declares `facts.jsonl` as an output (`stages.py` ~55–66) but that name is not in `name_map` — existence only. `cross_group_edges.json` is existence-only. `capacity_preflight` declares no `outputs` at all (`stages.py` ~98–113). Truncated `--until` / scan-only paths may never hit later `validate_artifacts --all` gates.

**Fix direction:** Drive validation from `ARTIFACT_FILENAMES` / `ARTIFACT_MODELS` keyed by filename (including JSONL `facts`); declare capacity report outputs.

---

### High

#### [High] H1 — Build-command allowlist admits shells + `startswith` prefixes

**Verdict:** CONFIRMED  
**Anti-pattern:** Over-broad allowlist / trust-boundary leak

```16:54:src/doc_engine/scanning/build_command.py
_ALLOWED_PREFIXES = (
    "gradlew",
    "gradle",
    "mvnw",
    "mvn",
    "bash",
    "sh",
    "cmd",
    "powershell",
)
...
    if not any(first_token == prefix or first_token.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
```

Metacharacters are rejected, but shells are first-class allowlist members, and `startswith` admits `mvnEvil`, `bashrc`, `powershell.exe`. Untrusted `.doc-engine.yml` / `--build-command` reaches CodeQL `database create --command=…`. No `shell=True` in Python — the RCE shape is via the allowed interpreter invocation.

**Fix direction:** Exact basenames only (`gradlew`, `gradle`, `mvnw`, `mvn`); drop shells for untrusted input; adversarial tests for `-c` / `/c` / `-File`.

---

#### [High] H2 — Conflicting `file_signatures` kept silently

**Verdict:** CONFIRMED  
**Anti-pattern:** Silent LWW / prose over reality  
**DDIA:** `replication-lag-and-lww`, `trust-but-verify`

```164:174:src/doc_engine/scanning/_merge_signals.py
def _merge_file_signatures(partials: List[Dict[str, Any]]) -> Dict[str, str]:
    """Merge file_signatures. All backends must agree on the hash for a file."""
    merged: Dict[str, str] = {}
    for partial in partials:
        for file_path, sig in partial.get("file_signatures", {}).items():
            if file_path in merged and merged[file_path] != sig:
                # Same file, different hash across backends is a serious inconsistency.
                # Keep the first and warn; callers should not get here for a normal repo.
                continue
            merged[file_path] = sig
    return merged
```

Comment says “warn”; body never logs. Covering inventory and drift tier-1 hashing assume one SoR hash per path; contradictory backends still produce a coherent-looking inventory.

**Fix direction:** Raise / fail the merge on signature conflict (fail closed).

---

#### [High] H3 — Manifest `end-stage` result ignored

**Verdict:** CONFIRMED  
**Anti-pattern:** Fire-and-forget side effect

`PipelineRunner._run_stage` (~83–97) runs `end-stage` via `subprocess_runner.run` and discards the `StageResult`. Stage body can succeed while the run manifest stays mid-stage; resume/finalize/drift against that manifest lie about completion.

**Fix direction:** Fail the stage (or abort the run) if `end-stage` is non-zero.

---

#### [High] H4 — Dual orchestration: `local_runner.Runner` + `PipelineRunner`

**Verdict:** CONFIRMED  
**Anti-pattern:** Parallel hierarchies / shotgun surgery on orchestration changes

`local_runner.py` defines its own gate/cert/`keep_going` subprocess `Runner` (~157+) and also constructs `PipelineRunner` for deterministic stages (~586–591) and later generative wiring (~685–687). Two recording models (`OK`/`FAIL`/`SKIPPED` vs `StageResult`), divergent timeout/abort semantics, dual maintenance with `live_gates.py`.

**Fix direction:** Keep `PipelineRunner` as the only stage-graph executor; thin CLI + gate runner + cert writer around it.

---

#### [High] H5 — Hardcoded developer CodeQL path

**Verdict:** CONFIRMED  
**Anti-pattern:** Environment coupling in library code

```47:49:src/doc_engine/scanning/support/_codeql_runner.py
CODEQL_DEFAULT_PATHS = [
    Path(r"C:\Users\16145\.cursor\tools\codeql\codeql.exe"),
]
```

Personal absolute path in the installable package. Other machines may silently pick a stale install if PATH is empty; username leaks into error paths.

**Fix direction:** PATH / `DOC_ENGINE_CODEQL` only; remove committed personal paths.

---

#### [High] H6 — Unreadable config files silently skipped (secrets fail-open)

**Verdict:** CONFIRMED  
**Anti-pattern:** Silent skip of a security control

`_process_config_deployment_file` in `_scanner_filesystem.py` (~47–51): `except OSError: return`. Permission-denied `application.yml` yields no `redaction_zones` and no config keys; downstream may treat the path as clean.

**Fix direction:** Emit an explicit unreadable receipt/evidence row and fail closed for that path (or covering-status failure).

---

#### [High] H7 — Unbounded subprocesses

**Verdict:** CONFIRMED  
**Anti-pattern:** Missing timeout / hang amplification

`SubprocessStageRunner.run` (`executor.py` ~25–32), `local_runner.Runner.run`, and CodeQL create/query paths call `subprocess.run` without `timeout=`. Hung `gradlew` / wedged CodeQL / stuck ast-grep holds CI and local certification forever.

**Fix direction:** Timeouts per tool class (scan vs build vs gate); document “no retry” or add idempotent retries only for known-transient errors.

---

### Medium

#### [Medium] M1 — God modules

**Verdict:** CONFIRMED  
Approx LOC: `scanning/gap_probe.py` ~1024; `tools/spring_drift_check.py` ~935; `pipeline/local_runner.py` ~836. Complexity concentrates where this repo’s own history already found termination bugs (`build_groups` / prompt 13).

**Fix direction:** Split measure vs I/O in gap_probe; split CLI / gates / cert in local_runner; keep drift check’s pure compare separate from CLI.

---

#### [Medium] M2 — Anemic `Signal = Dict[str, Any]`

**Verdict:** CONFIRMED  
`core/protocols.py` aliases `Signal = Dict[str, Any]`; merge/orchestrator are procedural dict surgery. Boundary Pydantic models exist; Stage 0 interior never uses them. Prompt 13’s still-open “typed cross-stage artifacts” is half-true: boundaries yes, interior no.

**Fix direction:** Validate-on-merge against `SpringSignalsArtifact`, or introduce typed interior bags with a clear evolution path.

---

#### [Medium] M3 — `input_artifacts` decorative

**Verdict:** CONFIRMED  
`StageSpec.input_artifacts` (`pipeline/context.py` ~51–52) is set in `build_stage_specs` and serialized by `generative_choreography()` (`stages.py` ~179) but **never** read by `PipelineRunner`. Vacuous contract field — adapters may assume the runner enforces prerequisites.

**Fix direction:** Preflight existence (and optionally schema) of `input_artifacts` before `_run_stage`.

---

#### [Medium] M4 — Duplicate DFS walks

**Verdict:** CONFIRMED  
`partition_repo.dfs_file_list` (~163–207) is separate from `core.walk.dfs_walk` (~12–32). Exclude / gitignore semantics can drift between Stage 0 inventory and partition inventory (covering proofs only close Stage 0’s walk).

**Fix direction:** Partition consumes shared walk helpers (or `ScanContext` paths) with one exclude policy.

---

#### [Medium] M5 — Schema asymmetry `extra="allow"` vs `forbid`

**Verdict:** CONFIRMED  
`EvidenceMatch` / `SpringSignalsArtifact` use `extra="allow"` (`artifacts.py` ~27, ~48); `Fact` uses `extra="forbid"` (~151). Path A can grow undocumented columns while still “validating.” Also `schema_version: Field(ge=2)` while merger emits `7` — ancient shapes can pass the boundary.

**Fix direction:** Tighten hot Path A fields; pin supported major(s); keep `extra="allow"` only for an explicit extension bag + deviation if intentional.

---

#### [Medium] M6 — N+1 source reads (scoped)

**Verdict:** CONFIRMED (entity-gated for ast-grep; every row for CodeQL)  
`java_extract.read_source_lines` opens and `readlines()`s the file per call (~56–61). Ast-grep calls it inside the match loop only for `persistence__entity` (`_scanner_astgrep.py` ~298–314). CodeQL calls it for every row (`_scanner_codeql.py` ~82–94). Dense hits re-read the same Java files repeatedly.

**Fix direction:** Per-scan file content cache keyed by `(rel, mtime/sig)`.

---

#### [Medium] M7 — Public `Engine` façade vs product path

**Verdict:** CONFIRMED (docs partially honest)  
`Engine.generate_docs` is placeholder (`engine.py` ~30–38); `build_site` mutates global `sys.argv` (~55–60). `docs/product-architecture.md` admits placeholders (~117–118). Package `__init__.py` still claims “language-agnostic documentation generation SDK” while Stage 0 is Spring/Java. CLI `docs`/`site` still ship.

**Fix direction:** Narrow `__init__` / `Engine` docs; prefer library calls over argv mutation; deprecate or hard-gate placeholder commands.

---

#### [Medium] M8 — Layering: scanning → pipeline

**Verdict:** CONFIRMED  
`scanning/gap_probe.py` imports `pipeline.artifacts`. Scan SDK depends on pipeline package → harder wheel split / pure scan extraction.

**Fix direction:** Move shared DTOs to `core` or `scanning.contracts`; pipeline re-exports.

---

#### [Medium] M9 — Agent trust boundaries + hook fail-open

**Verdict:** CONFIRMED  
Agents under `adapters/claude/agents/` declare `Write` / bare `Bash`; path discipline is prompt + project `.claude/settings.json`, not plugin-self-contained allowlists. `deny_raw_network` / `deny_text_search` fail open on bad JSON (exit 0). Network deny covers `curl`/`wget`/`git clone` only.

**Fix direction:** PreToolUse path allowlist for Write; ship deny+allow with plugin or remove Bash; audit on hook parse failure; document marketplace-without-settings as unsafe.

---

### Low / documentation drift

#### [Low] L1 — Steering prompt 02 body stale

**Verdict:** CONFIRMED  
`claude/steering-prompts/02-pluggability-research-prompt.md` `verify:` correctly points at `src/doc_engine/tools/validate_artifacts.py` and `pipeline_validators.py`, but the body (~25) still cites `scripts/validate_artifacts.py` / `scripts/pipeline_validators.py` (absent). Classic prose-over-reality; `check_repo_claims` cannot catch body text.

---

#### [Low] L2 — `HttpLLMStageExecutor` stub vs hexagonal marketing

**Verdict:** CONFIRMED  
`executor.py` stub always returns failure (~70–84). `pipeline/adapters.md` correctly notes Claude generative stages are out-of-process. Product-architecture “hexagonal / adapters” language still oversells in-process adapter depth.

---

## 4. Disproved / non-findings

| Hypothesis | Verdict | Note |
|------------|---------|------|
| “No modern design patterns in use” | REFUTED | Stage 0 registry/Strategy/covering barrier are real and documented |
| `shell=True` RCE in Python subprocesses | REFUTED | None found; argv lists throughout |
| Semgrep missing as Stage-0 Strategy backend | REFUTED (as defect) | Semgrep is coverage/meta under `scripts/coverage/` by design |
| `Engine` placeholders completely undocumented | REFUTED | `product-architecture.md` already flags them; bite is `__init__` + CLI still shipping as productive |
| Every ast-grep match does N+1 `read_source_lines` | REFUTED | Entity-gated only; CodeQL every-row claim stands |

---

## 5. Remediation waves

Each wave closes a **failure class**, not a one-off (prompt 10). **Not implemented in this pass** — separate explicit approval required.

### Wave 1 — make gates real (highest bite / smallest blast radius)

1. Catch `ArtifactValidationError` (+ JSON decode errors) in `PipelineRunner` → stage fail.  
2. Expand `_validate_outputs` via `ARTIFACT_FILENAMES` / models; declare capacity outputs.  
3. Fail closed on signature hash conflict (raise, don’t `continue`).  
4. Honor `end-stage` failure; add subprocess timeouts.  
5. Tighten `validate_build_command` (exact tool basenames; no shells).  
6. Remove hardcoded CodeQL user path.

### Wave 2 — orchestration SRP

Collapse dual `Runner` / `PipelineRunner` recording; split `local_runner` (CLI / gates / cert); preflight `input_artifacts`.

### Wave 3 — domain + perf

Typed interior signals (or validate-on-merge); shared walk for partition; per-scan file content cache for `read_source_lines`; tighten Path A `extra` policy (deviation entry if intentional looseness remains).

### Wave 4 — documentation that bites

Fix `__init__.py` “language-agnostic” claim; refresh prompt 02 body paths; align hexagonal language with “CLI + out-of-process generative adapters”; constrain agent Write/Bash mechanically where feasible.

---

## 6. Pattern scorecard (summary)

| Axis | Assessment |
|------|------------|
| Creational | Registry/factory and ctor DI on `PipelineRunner` are sound; scattered construction and false `Engine` façade hurt |
| Structural | Ports + ABC backends + boundary DTOs work; dual runners and scanning→pipeline import invert layering |
| Behavioral | Stage strategy + covering barrier excel; decorative `input_artifacts` and ignored `end-stage` undercut the template lifecycle |
| Integrity | Covering proofs fail closed; signature merge and schema escape fail open |
| Security | No `shell=True`; build-command allowlist and unreadable-config skip are the sharp edges |
| Docs | Hot WHY modules and DDIA north-star are excellent; package `__doc__` and prompt bodies lag reality |

**Bottom line:** Treat Stage 0’s covering/Strategy design as the template. Bring `PipelineRunner` error handling, artifact contracts, and subprocess hygiene up to that same fail-closed bar, then carve the god orchestration modules so those contracts stay reviewable.
