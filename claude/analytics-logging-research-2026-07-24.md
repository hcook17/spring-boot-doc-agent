---
category: Analytics & logging (run-level telemetry) — research pass
status: research complete; schema proposal ready to hand to implementation
research date: 2026-07-24
---

# Research: prior art for `run_manifest.json` (the still-open half of `04-analytics-logging-research-prompt.md`)

Self-contained. Read `claude/steering-prompts/00-shared-research-standards.md` first for the methodology this follows, and `claude/steering-prompts/04-analytics-logging-research-prompt.md` for what's already resolved (drift detection, via `spring_drift_check.py`) versus what's still open (run-level telemetry — this doc).

## 1. Did `spring_drift_check.py` diverge from established doc-drift-detection practice? (arXiv)

The 04 prompt says this is only worth researching "if `spring_drift_check.py`'s own approach ... turns out to diverge from established practice in a way worth reconsidering." Read the actual file (`claude/pending-delivery/spring_drift_check.py`) in full before this search: it's a two-tier deterministic checker — Tier 1 whole-repo sha256 file-signature diff, Tier 2 for changed files only, targeted `ast-grep` re-run with per-rule-type identity extraction (entity class name, repository interface name, extracted query text — not raw match text), multiset (`Counter`)-based comparison. Zero LLM calls anywhere in the file, by explicit design.

Searched arXiv (`documentation drift detection`, `doc-to-code traceability`) and confirmed by opening abstracts, not just titles:

- **DocSync** (arXiv:2605.02163, May 2026) — "agentic documentation maintenance via critic-guided reflexion." LLM-agent-based, not deterministic.
- **CASCADE** (arXiv:2604.19400, Apr 2026) — detects code/doc inconsistency via *automatic test generation*. Different mechanism class entirely (dynamic/test-based, not static hash+AST).
- **DocPrism** (arXiv:2511.00215, Nov 2025) — "local categorization and external filtering" for code-doc inconsistencies. Conceptually closest in *shape* (a cheap local filter before a more expensive check) but the actual mechanism is LLM-based categorization + filtering, not a content hash + structural re-derivation.
- **ReqToCode** (arXiv:2603.13999) — solves traceability by *generating* code-native "Traceable" elements checked at compile time. Not applicable here: this pipeline has no compile step and isn't generating the target repo's code, only documenting it. Also note: single-author, "Independent Researcher," no venue listed — lower-confidence source, flagged as such rather than cited as settled practice.
- **R2Code** (arXiv:2604.22432) and **Remember Your Trace** (arXiv:2605.14563) — both LLM/agent-based traceability or documentation generation, same pattern as above.

**Finding, tagged confirmed (abstracts opened directly, not inferred from title):** every current-literature approach found for this problem class is either LLM-based (reflexion/agentic categorization) or dynamic/test-generation-based. None uses `spring_drift_check.py`'s specific combination — deterministic content hashing as a cheap coarse filter, gated to a targeted, per-rule-type structural re-derivation via an existing parser (`ast-grep`) as the precise check, with zero model calls. That's a legitimate, more lightweight point in the design space than what recent papers explore, not a gap relative to them — this pipeline already has `ast-grep` as a dependency and no need to invoke an LLM just to answer "is this specific citation still true." **Conclusion: no divergence worth reconsidering. Don't redesign drift detection based on this pass.**

## 2. Run-manifest / provenance-log schema prior art (GitHub, star/push-filtered)

Applying `00-shared-research-standards.md`'s two-signal filter (star floor ~300–500 for a tooling repo, checked *actual* recent push/release activity, not just creation date):

| Repo | Stars | Recency signal (confirmed directly) | Verdict |
|---|---|---|---|
| [mlflow/mlflow](https://github.com/mlflow/mlflow) | 25.9k | v3.12.0 released May 5, 2026 | Current, both signals strong |
| [wandb/wandb](https://github.com/wandb/wandb) | 11.1k | v0.27.2 released Jun 6, 2026 | Current, both signals strong |
| [google/ml-metadata](https://github.com/google/ml-metadata) | 683 | v1.21.0 released Jun 9, 2026 | Current, both signals strong |
| [in-toto/attestation](https://github.com/in-toto/attestation) | 341 | v1.2.0 released Mar 18, 2026; CNCF-governed | Right at the star floor, but recency + CNCF governance justify inclusion — noted explicitly per the "say so plainly" rule rather than smoothed over |
| [iterative/dvc](https://github.com/iterative/dvc) | 15.8k | Actively maintained per current docs; exact last-push timestamp not directly confirmable via the pages fetched | Strong star signal; recency confirmed only indirectly (docs freshness), flagged as such |
| [IDSIA/sacred](https://github.com/IDSIA/sacred) | 4.4k | Last *release* Nov 26, 2024 (~20 months stale as of this research date) | High stars but stale by this project's own recency rule — used below only as the historical origin of the "Ingredients/Observers" pattern, not as current best practice |

DeepWiki indexing checked for the top candidates (`deepwiki.com/<org>/<repo>`): pages exist for `google/ml-metadata`, `mlflow/mlflow`, and `in-toto/attestation`, but their top-level overview pages didn't carry the specific field-level schema detail needed — each said so explicitly rather than fabricating a schema, and pointed at the underlying `.proto`/source files. Per the methodology (DeepWiki as orientation, not as the cited source), the actual field lists below are drawn from the primary source files themselves, fetched and read directly:

**MLflow `RunInfo`** (`mlflow/entities/run_info.py`, confirmed via direct fetch): `run_id`, `experiment_id`, `user_id`, `status` (enum), `start_time`/`end_time` (ms since epoch), `lifecycle_stage`, `artifact_uri`, `run_name`.

**ML Metadata `Execution`** (`ml_metadata/proto/metadata_store.proto`, confirmed via direct fetch): `id`, `name`, `type`/`type_id`, `last_known_state` — enum `UNKNOWN | NEW | RUNNING | COMPLETE | FAILED | CACHED | CANCELED` — `properties`/`custom_properties` (typed vs. free-form key-value), `create_time_since_epoch`/`last_update_time_since_epoch` (ms). Relationships (execution → artifact) captured via separate `Event`/`Attribution`/`Association` records, not inline. This is the closest match in the set to "per-stage timing + pass/fail state" — it's literally designed for pipeline-run lineage (TFX), the same shape of problem as this plugin's five-stage pipeline.

**in-toto Link predicate** (`spec/predicates/link.md`, confirmed via direct fetch): `name`, `command` (list), `materials` (inputs, each a name+digest pair), `byproducts` (opaque dict), `environment` (opaque dict); the enclosing Statement adds `subject` (outputs, i.e. products) and `predicateType`. The materials/products split, plus an opaque `environment` bag for anything that doesn't need a fixed schema, is a clean model for "target repo path + commit hash" plus arbitrary future fields without a schema migration.

**DVC `dvc.lock`** (`doc.dvc.org`, confirmed via direct fetch): top-level `schema: '2.0'` version string, then per-stage `cmd`, `deps` (path + content hash), `params` (key/value from a params file), `outs` (path + hash + size). This is the closest direct analog to what this plugin already half-has — `spring_signals.json`'s own `schema_version` field and `file_signatures` map are structurally the same idea as `dvc.lock`'s versioned, per-stage, hash-keyed dependency record. That convention is worth keeping consistent with rather than reinventing.

## 3. Recommended `run_manifest.json` schema

Synthesized from the above, scoped per `00-shared-research-standards.md`'s "no new dependencies" rule — plain JSON, stdlib-only, no new services (no MLflow/W&B/ML Metadata server, no protobuf). Reuses the `schema_version` convention already established in `spring_signals.json` rather than introducing a second one (see `02-pluggability-research-prompt.md`'s note that this convention already exists informally — formalize it, don't compete with it).

```json
{
  "schema_version": 1,
  "run_id": "2026-07-24T18:03:11Z-<short-hash>",
  "target_repo": {
    "path": "/abs/path/to/repo",
    "commit_hash": "a1b2c3d..."
  },
  "timestamp_start": "2026-07-24T18:03:11Z",
  "timestamp_end": "2026-07-24T18:11:47Z",
  "status": "complete",
  "stages": [
    {
      "name": "scan",
      "status": "complete",
      "start_time_ms": 1721847791000,
      "end_time_ms": 1721847812000,
      "duration_ms": 21000,
      "error": null
    }
  ],
  "file_signatures": {
    "src/main/java/.../InvoiceService.java": "sha256:..."
  },
  "evidence_tag_counts": {
    "readme.md": { "Evidenced": 12, "Confirmed": 3, "Unknown": 1, "PerExistingDocs": 0 }
  },
  "interview": {
    "asked": 9,
    "answered": 7,
    "skipped": 2,
    "questions": [
      { "id": "integrations.who-calls-us", "status": "answered" }
    ]
  }
}
```

Design notes, each tied to a specific source above:

- `schema_version` + per-run hash-keyed `file_signatures`, versioned the same way `dvc.lock` and `spring_signals.json` already are — **not** a new convention.
- `status` per stage uses ML Metadata's `Execution.last_known_state` enum vocabulary (`new | running | complete | failed | cached | canceled`) rather than inventing a bespoke one — `cached`/`canceled` are worth keeping even though this pipeline doesn't use them yet, since they're the two states most likely to matter once `check-drift`-before-rerun (04's item 1) is wired in and a re-run can legitimately skip/cache a stage.
- `target_repo.commit_hash` + `file_signatures` is exactly what 04's spec asked for — this is the field that lets `run_manifest.json` feed `spring_drift_check.py` directly as its "prior scan" input, instead of requiring a separate `spring_signals.json` copy.
- Materials/products/environment split from in-toto's Link predicate is *not* adopted verbatim (it would add a layer of indirection this five-stage, single-repo pipeline doesn't need) but its principle — a fixed set of fields for what's known now, plus one deliberately-unstructured bag (here, none needed yet; add one if a future stage needs it) rather than a rigid schema that has to be migrated for every addition — informed keeping `stages[].error` a free-text field rather than a structured error taxonomy that doesn't exist yet.
- `evidence_tag_counts` and `interview` are this plugin's own domain-specific additions — no prior-art system reviewed has an equivalent, since none of them run a live human interview step per `comparable-tools-benchmark.md`'s Assessment 2 finding (the evidenced/confirmed/unknown tri-state itself was already confirmed there as a novel combination, not something to re-derive schema for elsewhere).

## What's still open after this research pass

This document is research + schema proposal only. Actually writing the emitter (a small stdlib module invoked once per pipeline run, plus the "surface a short human-readable summary at the end of a run" requirement from 04's item 3) is unbuilt — same status as before this pass, just now schema-informed rather than schema-less. Recommend implementing directly against the schema above rather than re-researching.
