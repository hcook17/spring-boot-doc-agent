# Adoption hardening checklist (F4)

Operational steps after the orchestrator and adapters land. No code required — run these before multi-team rollout.

## 1. Branch protection on `main`

CI exists ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) but merges are not gated. Enable required status checks (repo admin):

```bash
gh api repos/:owner/:repo/branches/main/protection \
  --method PUT \
  --field required_status_checks[strict]=true \
  --field required_status_checks[contexts][]=test \
  --field enforce_admins=false \
  --field required_pull_request_reviews[required_approving_review_count]=1
```

Adjust `contexts` to match your required check names. See [`CONSTRAINTS.md`](CONSTRAINTS.md) enterprise-readiness item 6.

## 2. Certified run on a real target repo

```bash
pip install -e .
doc-engine pipeline run /path/to/target-repo \
  --compliance-profile certified \
  --out-dir /tmp/doc-certified-run
doc-engine certification verify /tmp/doc-certified-run/certification.json
```

Use `--docs-in-target-repo` so `check_pipeline_output` exercises the stray-write gate. Review `certification.json` — expect `generative_executor: mock` for local runs; live adapters should record `live`.

## 3. Semantic pipeline eval (once)

After a real completed run (live generative stages via Claude adapter):

1. Set `PIPELINE_ARTIFACTS_DIR` to the run output directory.
2. Follow [`adapters/claude/skills/semantic-pipeline-eval/SKILL.md`](adapters/claude/skills/semantic-pipeline-eval/SKILL.md).
3. Human review escalated findings.

## 4. Capacity preflight on largest intended repo

```bash
python -m doc_engine.tools.capacity_preflight /path/to/largest-service \
  --groups-file ... --signals-file ... --out capacity_preflight_report.json
```

Recalibrate warning thresholds in [`adapters/claude/skills/capacity-preflight/SKILL.md`](adapters/claude/skills/capacity-preflight/SKILL.md) if defaults fire on normal mid-size services.

## 5. First live generative run at scale

Only Stage 0 has been exercised on a ~615-file service. Close the manifest predicted-vs-actual fan-out loop by running Stages 1–4 live once and comparing `run_manifest.json` to `capacity_preflight_report.json`.
