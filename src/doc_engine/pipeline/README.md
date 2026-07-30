# Pipeline bounded contexts and artifact flow

Context map for org customers: which stage owns which artifact and what each handoff validates.

```mermaid
flowchart LR
  subgraph stage0 [Stage0_Deterministic]
    Scan[spring_signal_scan]
    Part[partition_repo]
    Edges[build_cross_group_edges]
  end

  subgraph artifacts [JSON_Artifacts]
    SS[spring_signals.json]
    G[groups.json]
    E[cross_group_edges.json]
    Sum[summaries.json]
    IA[interview_answers.json]
  end

  subgraph generative [Generative_Stages]
    FS[file_summarize]
    Arch[architect]
    Gap[gap_analysis_interview]
    DW[doc_writer]
  end

  Scan --> SS
  Part --> G
  SS --> Edges
  G --> Edges
  Edges --> E
  SS --> FS
  G --> FS
  E --> FS
  FS --> Sum
  Sum --> Arch
  Sum --> Gap
  SS --> Gap
  Sum --> DW
  IA --> DW
  SS --> DW
```

## Bounded contexts

| Context | Responsibility | System of record |
|---------|----------------|------------------|
| Evidence scan | ast-grep/CodeQL signals, entity-table map, file signatures | `spring_signals.json` |
| Partitioning | token-bounded DFS groups | `groups.json` |
| Cross-group join | deterministic package/import edges | `cross_group_edges.json` |
| Summarization | per-file semantic summaries + line anchors | `summaries.json` |
| Architecture | Mermaid diagram fragments + merge | `architecture_merged.md` |
| Interview | human facts static analysis cannot see | `interview_answers.json` |
| Doc emission | fourteen taxonomy markdown files | `docs/*.md` |

## Validation at boundaries

Prefer the CLI facade (A+C hybrid):

```bash
doc-engine pipeline run <repo> --compliance-profile deterministic_only --out-dir <run>
doc-engine pipeline gates --out-dir <run> --target-repo <repo> --docs-dir <docs>
```

From a product checkout:

```bash
python -m doc_engine.tools.validate_artifacts --all <run-directory>
```

Mechanical shape gates (summaries, gap questions) live in `doc_engine.tools.pipeline_validators`.

Schemas: `scripts/schemas/*.schema.json` (derived from `doc_engine.pipeline.artifacts`).
`facts.jsonl` is JSON Lines (`JSONL_ARTIFACTS`); other registered artifacts are single JSON values.

## Import vs CLI boundaries

| Consumer | Import | Invoke |
|----------|--------|--------|
| Tests | `doc_engine.pipeline.*`, `doc_engine.tools.*` | In-process |
| Claude skills | — | `doc-engine pipeline run\|gates`, `certification verify` only |
| Operators / CI | — | same CLI, or `python -m doc_engine.tools.*` |

## Code entry points

- `PipelineRunner` — `src/doc_engine/pipeline/runner.py`
- `PipelineContext` — paths, repo, manifest, in-run state
- `MockStageExecutor` — local E2E without LLM
- `local_runner.py` — orchestration, gates wiring, certification finish; supports `--until STAGE`
- `live_gates.py` — post-generative gate suite for live adapters
- `mock_stages.py` — mock generative stage writers
- `gates.py` — in-process mechanical gate runners (`validate_artifacts`, `pipeline_validators`)

Stage graph SoT: `build_stage_specs()` in `stages.py`. Skills must not reintroduce per-script bash under the plugin root.
