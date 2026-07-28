# doc-engine product architecture

This repository ships **doc-engine** — a portable orchestrator for documenting Spring Boot repositories — not a Claude-plugin-shaped monolith.

## Three layers

| Layer | What | Where |
|-------|------|--------|
| **Kernel** | `PipelineRunner`, scanning SDK, compliance profiles, CLI | `src/doc_engine/` (pip package `doc-engine`) |
| **Pipeline tools** | Stage 0 scripts, gates, validators (today `scripts/`) | Bundled with the repo; moving into `doc_engine.tools` over time |
| **Adapters** | Optional entry points (Claude, GitHub Actions, Cursor) | `adapters/` |

**Target-repo context** (customer Spring service) is never part of this tree:

- `.doc-engine.yml` — `compliance_profile`, scanners, dialect
- Pipeline artifacts + `certification.json` — written to `--out-dir` on each run

## Portable install (any company, any repo)

```bash
pip install -e .   # or a published wheel when available
cd /path/to/customer-spring-service

# optional .doc-engine.yml
doc-engine pipeline run . --out-dir /tmp/doc-run
doc-engine certification verify /tmp/doc-run/certification.json
```

No clone of this meta-repo is required in the customer tree. No `agents/` folder in their project.

## Compliance and certification

Profiles (`scan_only`, `deterministic_only`, `certified`) drive which stages and gates run. Every `doc-engine pipeline run` writes `certification.json`.

| `certified` | Meaning |
|-------------|---------|
| `true` | All required stages and mechanical gates for the profile passed |
| `false` | See `failures` array in the report |

`generative_executor: mock` under `certified` means **structural** compliance (wiring + gates), not human-quality prose. Production Claude/Cursor runs should record `live` when real LLM stages execute.

## Adapters

| Adapter | Path | Role |
|---------|------|------|
| CLI | `doc-engine pipeline run` | Primary entry; writes `certification.json` |
| Certification | `doc-engine certification verify` | Exit 0 only when `certified: true` |
| Local script | `scripts/run_pipeline_local.py` | Same orchestration; thin script entry |
| GitHub | `adapters/github/` + root `action.yml` | CI gate on `certification.json` |
| Claude Code | `adapters/claude/` | Plugin pack: agents, hooks, skills |
| Cursor | `adapters/cursor/` | Call the CLI from automations |

Kernel code does **not** import from `adapters/claude/agents/` or resolve paths via `CLAUDE_PLUGIN_ROOT`. Adapters call the kernel.

See also [`src/doc_engine/pipeline/adapters.md`](src/doc_engine/pipeline/adapters.md).

## Design pattern map (architectural)

| Pattern | Files | Role |
|---------|-------|------|
| Hexagonal / ports-adapters | `pipeline/executor.py`, `adapters/` | Kernel ports; adapters call inward |
| Orchestration | `pipeline/runner.py`, CLI | Central stage graph |
| Choreography | Claude SKILL + agents | Generative fan-out outside kernel |
| Plugin registry | `scanning/_scanner_registry.py` | Scanner backends |
| Anti-corruption layer | `pipeline/artifacts.py`, `validation.py` | JSON boundary DTOs |
| Gateway | `tools/certification.py`, compliance gates | Machine enforcement |
| Strangler fig | `tools/`, `paths.py` | Absorbing `scripts/` incrementally |
| Twelve-factor config | `.doc-engine.yml`, CLI overrides | Portable target-repo policy |

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
| Facade | `cli.py` | Single CLI entry |
| Bootstrap | `tools/_bootstrap.py` | One sanctioned `sys.path` path into `scripts/` |

Legacy `Engine.generate_docs()` / `build_site()` are placeholders — use `doc-engine pipeline run` for real orchestration.

## Agent search policy

Claude agents must not use text search for code citations. See [`adapters/claude/SEARCH.md`](adapters/claude/SEARCH.md) and [`docs/search-methodology-benchmark.md`](search-methodology-benchmark.md).
