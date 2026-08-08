# doc-engine product architecture

This repository ships **doc-engine** — a portable orchestrator for documenting Spring Boot repositories — not a Claude-plugin-shaped monolith.

## Locked design: A+C hybrid

| Axis | Choice |
|------|--------|
| Claude skill role | **A — generative-only** (interview + Task agents). Deterministic tools are never invoked via `${CLAUDE_PLUGIN_ROOT}/scripts/`. |
| Stage-graph SoT | **C — `build_stage_specs()` / compliance profiles**. Skills may cite `doc-engine pipeline run` profiles and optional `--until STAGE`; they must not duplicate per-script bash. |
| Plugin contents | Agents, hooks, skills, SEARCH.md, short CONSTRAINTS stub only |
| Public CLI facade | `pipeline run` (+ `--until`), `pipeline gates`, `certification verify`, `scan` |

This closes the marketplace packaging gap created when F3/R3 moved `source` to `adapters/claude` without rewriting skills: the plugin cache has no `scripts/` tree, so plugin-local script paths cannot be the product contract.

## Three layers

| Layer | What | Where |
|-------|------|--------|
| **Kernel** | `PipelineRunner`, scanning SDK, compliance profiles, CLI | `src/doc_engine/` (pip package `doc-engine`) |
| **Pipeline tools** | Stage 0 tools, product gates, validators — live under `doc_engine.tools` (one invoke surface) | Invoked by the CLI / `local_runner`, not by the Claude plugin |
| **Adapters** | Optional entry points (Claude, GitHub Actions, Cursor) | `adapters/` |

**Target-repo context** (customer Spring service) is never part of this tree:

- `.doc-engine.yml` — `compliance_profile`, scanners, dialect
- Pipeline artifacts + `certification.json` — written to `--out-dir` on each run

## Product vs meta boundary

This monorepo holds two runtimes. Mixing them into the installable package couples customer installs to this repo's self-check policy.

| Runtime | May enter `doc_engine` / the wheel | Stays in `scripts/` (meta only) |
|---------|-------------------------------------|----------------------------------|
| **Product** | Stage 0 tools (`run_manifest`, `spring_signal_scan` / scanning SDK, `partition_repo`, `build_cross_group_edges`, `capacity_preflight`), product gates used by `live_gates` / certification (`check_pipeline_output`, `citation_coverage`, `check_no_secrets_leaked`, validators), runtime schemas and scan resources, `doc_tag_utils`, `build_docs_site` | — |
| **Meta** | — | `check_repo_claims`, `check_code_quality`, `mutate`, `rule_coverage`, `semgrep_rule_coverage`, `check_llms_coverage`, research instruments (`stage0_oracle_compare`, …), and this repo's quality baselines |

**Portable Stage 0:** skills invoke the CLI (A+C). Deterministic stages run via package entrypoints (`python -m doc_engine.tools.*` / `doc-engine`) so `pip install` works without cloning this monorepo. Product tools are not dual-homed under `scripts/`.

## Portable install (any company, any repo)

```bash
pip install -e .   # or a published wheel when available
cd /path/to/customer-spring-service

# optional .doc-engine.yml
doc-engine pipeline run . --out-dir /tmp/doc-run
doc-engine certification verify /tmp/doc-run/certification.json
```

No clone of this meta-repo is required in the customer tree. No `agents/` folder in their project.

First pilot walkthrough (Path A deterministic, Path B full Claude): [`guides/operator-pilot.md`](guides/operator-pilot.md). Org rollout brief for principals: [`guides/principal-adoption.md`](guides/principal-adoption.md).

## Compliance and certification

Profiles (`scan_only`, `deterministic_only`, `certified`) drive which stages and gates run. Every `doc-engine pipeline run` writes `certification.json`.

| `certified` | Meaning |
|-------------|---------|
| `true` | All required stages and mechanical gates for the profile passed |
| `false` | See `failures` array in the report |

`generative_executor: mock` under `certified` means **structural** compliance (wiring + gates), not human-quality prose. Production Claude/Cursor runs should record `live` when real LLM stages execute.

Live adapter flow after Stage 0:

```bash
doc-engine pipeline run <repo> --compliance-profile deterministic_only --out-dir <run>
# … generative agents + interview …
doc-engine pipeline gates --out-dir <run> --target-repo <repo> --docs-dir <docs>
```

## Adapters

| Adapter | Path | Role |
|---------|------|------|
| CLI | `doc-engine pipeline run` / `pipeline gates` | Primary entry; writes / checks certification |
| Certification | `doc-engine certification verify` | Exit 0 only when `certified: true` |
| Local runner | `python -m doc_engine.pipeline.local_runner` / `doc-engine pipeline run` | Same orchestration |
| GitHub | `adapters/github/` + root `action.yml` | CI gate on `certification.json` |
| Claude Code | `adapters/claude/` | Plugin pack: agents, hooks, skills (generative only) |
| Cursor | `adapters/cursor/` | Call the CLI from automations |

Kernel code does **not** import from `adapters/claude/agents/` or resolve paths via `CLAUDE_PLUGIN_ROOT`. Adapters call the kernel.

See also [`src/doc_engine/pipeline/adapters.md`](../src/doc_engine/pipeline/adapters.md).

## Design pattern map (architectural)

| Pattern | Files | Role |
|---------|-------|------|
| Hexagonal / ports-adapters | `pipeline/executor.py`, `adapters/` | Kernel ports; adapters call inward |
| Orchestration | `pipeline/runner.py`, CLI | Central stage graph |
| Choreography | Claude SKILL + agents | Generative fan-out outside kernel |
| Plugin registry | `scanning/_scanner_registry.py` | Scanner backends |
| Anti-corruption layer | `pipeline/artifacts.py`, `validation.py` | JSON boundary DTOs |
| Gateway | `tools/certification.py`, compliance gates | Machine enforcement |
| Strangler fig (complete for product tools) | `tools/`, scanning SDK | Product left `scripts/`; meta CI stays there |
| Twelve-factor config | `.doc-engine.yml`, CLI overrides | Portable target-repo policy; see untrusted defaults below |

### Target-repo `.doc-engine.yml` trust

Customer Spring trees are **untrusted by default**. Without `--trust-repo-config`, the kernel ignores security-sensitive keys from the target's `.doc-engine.yml` (`build_command`, `db_path`, `scanners`, and any `compliance_profile` weaker than `certified`). Non-executing keys (`sql_dialect`, `respect_gitignore`, `doc_taxonomy`) still apply; YAML `extra` is cleared. Operator CLI flags (`--build-command`, `--scanners`, `--compliance-profile`, …) always win. Pass `--trust-repo-config` only when you intend to honor that file's sensitive keys.

**CodeQL build mode is refused by default.** `codeql database create --command` executes the build inside `--source-root` (attacker-controlled `gradlew`/`pom`). Pass `--allow-codeql-build` only for first-party trees or a sandboxed host. The build-command allowlist (exact basenames; `bash`/`sh` may wrap a tool; flags like `-I`/`--init-script`/`-s` rejected) is foot-gun hygiene, not an untrusted-tree control. CodeQL CLI discovery uses `DOC_ENGINE_CODEQL` then `PATH` — never a machine-local hardcoded path. Results cache lives under the user cache dir (`0700`), keyed by repo + pack + CLI version, and refuses symlink hijack.

External catalogs ([awesome-design-patterns](https://github.com/DovAmir/awesome-design-patterns), [microservices.io](http://microservices.io/patterns)) inform naming only — this repo's constraints (`CONSTRAINTS.md`) are authoritative.

## Python module conventions

| Pattern | Where | Notes |
|---------|-------|-------|
| `typing.Protocol` | `StageExecutor`, `Scanner` | Structural ports |
| ABC | `ScannerBackend` | Concrete scanner implementations |
| Registry + factory | `SCANNERS`, `get_scanner()` | Stage 0 backends |
| Strategy | `MockStageExecutor`, `SubprocessStageRunner` | Generative vs deterministic |
| Dataclass | `PipelineContext` | In-process orchestration state |
| Pydantic | `artifacts.py`, compliance models | Artifact contracts |
| Facade | `cli.py` | Single CLI entry (`pipeline run` / `gates` / `certification`; `docs`/`site` are placeholders) |
| ~~Bootstrap~~ | deleted | Former `tools/_bootstrap.py` path-hack removed; use `pip install -e .` |

Legacy `Engine.generate_docs()` / `build_site()` are placeholders — use `doc-engine pipeline run` for real orchestration.

## Import vs CLI boundaries

| Consumer | Import | Invoke |
|----------|--------|--------|
| Unit/integration tests | `doc_engine.*` | In-process |
| SKILL / operators | — | `doc-engine pipeline …` / `certification …` |
| Operators / CI | — | `python -m doc_engine.tools.<mod>` or `doc-engine …` |
| Kitchen-sink | package imports + `-m` subprocess | Explicit boundary tests |

## Agent search policy

Claude agents must not use text search for code citations. Prefer
`doc-engine query context-packet` for vague tasks when a run dir exists, then
specialized `doc-engine query` kinds, then `ast-grep` for live structural gaps.
Optional MCP: [`adapters/mcp/`](../adapters/mcp/). See
[`adapters/claude/SEARCH.md`](../adapters/claude/SEARCH.md) and
[`docs/search-methodology-benchmark.md`](search-methodology-benchmark.md).

## Design north star (DDIA)

Principal-grade design vocabulary (domains, relationships, chapter 5W1H, explicit deviations): [`docs/design/ddia-north-star/`](design/ddia-north-star/).
