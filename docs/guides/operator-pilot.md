# Operator pilot: document a Spring Boot repository (Path A and Path B)

This guide walks you through using **doc-engine** on a real Spring Boot service for the first time. You do not need prior experience with this project. Follow the steps in order.

**If this guide and the live skill or CLI disagree, the skill / CLI wins.** The generative stage list lives in [`adapters/claude/skills/document-spring-repo/SKILL.md`](../../adapters/claude/skills/document-spring-repo/SKILL.md) and in the code (`build_stage_specs()`). This file teaches *how to run*, not a second copy of the stage list.

For org rollout decisions (not step-by-step commands), see [`principal-adoption.md`](principal-adoption.md).

---

## 1. What you are doing

You will point this tool at a **Spring Boot** codebase (the *target* repository) and:

- **Path A — Deterministic only:** Scan the code with no AI writing documentation. You get structured JSON evidence (entities, controllers, security annotations, and more) plus a certification report for that scan profile.
- **Path B — Full pipeline:** Use that evidence plus Claude (AI assistants) to produce **fourteen** markdown documentation files, after a short human interview for questions code cannot answer.

### Glossary (read once)

| Term | Meaning |
|------|---------|
| **Repository (repo)** | A project folder that contains source code and usually a `.git` directory. |
| **This product repo** | The `spring-boot-doc-agent` checkout where you run `pip install`. It is *not* the service you are documenting. |
| **Target repo** | The Spring Boot service you want documented. |
| **PATH** | The list of folders your computer searches for programs. If `ast-grep` is “on PATH,” you can type `ast-grep` in a terminal and it runs. |
| **CLI** | Command-line interface — programs you run by typing commands (here: `doc-engine`). |
| **Stage 0** | The first, fully automatic scan. No large language model writes docs in Stage 0. |
| **Compliance profile** | A named mode that decides how much of the pipeline runs (`scan_only`, `deterministic_only`, `certified`). |
| **out-dir** | A folder you choose where run artifacts (JSON files, certification) are written. |
| **Certification** | A small JSON report (`certification.json`) saying whether required checks for that profile passed. |
| **Markdown (.md)** | Plain-text files with light formatting; the fourteen docs are markdown. |

---

## 2. What you need before starting

### Hardware / software

1. **Python 3.11 or newer** installed. Check: `python --version` (or `python3 --version`).
2. A **git clone** of *this* product repository (so you can `pip install -e .`).
3. The **full path** to a Spring Boot *target* repository on your machine.
4. Network access once, to download Python packages with `pip`.

### Install (in the product repository)

Open a terminal. On Windows, PowerShell is fine. Prefer **absolute paths** (full paths from the drive letter or `/`).

**Unix / macOS example:**

```bash
cd /home/you/src/spring-boot-doc-agent
pip install -r requirements.txt
pip install -e .
```

**Windows (PowerShell) example:**

```powershell
cd C:\Users\you\Downloads\spring-boot-doc-agent
pip install -r requirements.txt
pip install -e .
```

### Confirm the install

```bash
doc-engine --help
ast-grep --version
```

Both commands must print help or a version number. If `ast-grep` is missing, Stage 0 will fail. Installing `requirements.txt` is the supported way to get the pinned `ast-grep-cli`. If you also installed `ast-grep` via `cargo` or `npm`, those can shadow each other on PATH — run `ast-grep --version` and see [`claude/tool-quirks.md`](../../claude/tool-quirks.md) if versions look wrong.

---

## 3. Pick a first target

1. Choose a **small or medium** Spring Boot service for the first run — not the largest monolith in your company.
2. Prefer a checkout that does **not** contain real production secrets in committed config files. The tool tries to *flag* secret-looking lines (redaction zones); that is a **heuristic**, not a guarantee. Do not treat generated docs as safe to publish without human review of config-related content.
3. Write down two paths you will reuse:
   - `<repo_path>` — the target Spring Boot root (folder that contains `pom.xml` or `build.gradle` / `build.gradle.kts`, or a multi-module root you intend to scan).
   - `<run_dir>` — an empty or new folder for this run’s outputs (for example `/tmp/my-service-doc-run` or `C:\Temp\my-service-doc-run`).

**Filled-in examples:**

```text
Unix:    repo_path=/home/you/src/payments-api
         run_dir=/tmp/payments-api-doc-run

Windows: repo_path=C:\src\payments-api
         run_dir=C:\Temp\payments-api-doc-run
```

---

## 4. Path A — Deterministic only (no AI writing docs)

Path A answers: “Can we scan this service and get usable evidence?” You do **not** need Claude for Path A.

### 4.1 Optional: capacity preflight

If the service might be large, estimate cost/scale first:

```bash
python -m doc_engine.tools.capacity_preflight <repo_path>
```

This prints numbers about how the repo would be partitioned and how much fan-out a full generative run might imply. Warnings mean “plan for a longer or costlier Path B,” not “stop.” For a first small service you may skip this.

### 4.2 Main Path A command

```bash
doc-engine pipeline run <repo_path> \
  --compliance-profile deterministic_only \
  --out-dir <run_dir>
```

**Windows (PowerShell)** — same idea, one line is fine:

```powershell
doc-engine pipeline run C:\src\payments-api --compliance-profile deterministic_only --out-dir C:\Temp\payments-api-doc-run
```

**Faster smoke** (scan-focused profile, less of the deterministic graph):

```bash
doc-engine pipeline run <repo_path> --compliance-profile scan_only --out-dir <run_dir>
```

Use `deterministic_only` for a real Path A pilot. Use `scan_only` only to check that scanning works at all.

### 4.3 What to open and how to read it

Inside `<run_dir>` you should see files such as:

| File | What it is |
|------|------------|
| `spring_signals.json` | Scan results: entities/tables, evidence buckets (controllers, security, queries, …), `redaction_zones`, config key sets. |
| `facts.jsonl` | Dual-emit fact ledger (evidence hits + `MAPS_TO` / contested multi-map). **Not** required for `certification.json` yet — Path A cert still keys off signals/groups/validators, not this file. |
| `groups.json` | How source files were grouped for later parallel work. |
| `cross_group_edges.json` | Cross-group relationships computed in Stage 0 (not guessed by an LLM). |
| `certification.json` | Whether this profile’s required checks passed (`certified: true` / `false`). |

**How to skim `spring_signals.json`:**

1. Open it in any editor.
2. Look for `entity_table_map` — class names mapped to table names when detected.
3. Look under `evidence` — lists of findings with file/line style citations.
4. Look at `redaction_zones` — lines the scanner thinks may hold secrets; do not copy those values into docs or tickets.
5. If a query has `"lineage": {"available": false, ...}`, that often means the SQL/JPQL was too complex for automatic lineage. That is expected for some queries; it is not an automatic failure of Path A.

**How to skim `certification.json`:**

- `"certified": true` for `deterministic_only` means the **mechanical** checks for that profile passed.
- If you see `generative_executor: mock`, that refers to mocked generative stages when a fuller profile is used — it does **not** mean human-quality prose was produced. Path A does not produce the fourteen docs.

### 4.4 Path A success criteria

- The command finishes with **exit code 0**.
- `spring_signals.json` exists and is not an empty stub when the target really is a Spring codebase.
- You can name at least one entity or controller-looking finding that matches something you know in the service (spot-check).

### 4.5 Common Path A failures

| Symptom | Likely cause | What to do |
|---------|--------------|------------|
| `ast-grep` / binary not found | Not on PATH | Re-run `pip install -r requirements.txt`; open a new terminal; check `ast-grep --version`. |
| `not a directory` / path errors | Wrong `<repo_path>` | Use the absolute path to the service root. |
| Almost empty signals | Not Spring / wrong root | Confirm Java sources and Spring annotations exist under that path. |
| Lineage `available: false` | Hard JPQL/SQL | Expected for many queries; not a Path A failure by itself. |

---

## 5. Path B — Full pipeline (Claude generates the fourteen docs)

Path B answers: “Can we turn evidence into the fourteen-file documentation set, with a human interview for what code cannot tell us?”

Do Path A successfully on the **same** target first.

### 5.1 Extra prerequisites for Path B

1. **Claude Code** (or your org’s equivalent) with this product’s Claude adapter / plugin available. Marketplace install pattern is in the root [`README.md`](../../README.md) Install section.
2. **`semgrep` on PATH** if the architecture/testing review agent runs (also pinned in `requirements.txt`).
3. Willingness to **answer interview questions** in the chat (or mark them skipped). Subagents cannot pause for you; the main conversation asks.

### 5.2 Mental model

```text
Stage 0 (CLI, deterministic)
    → AI agents summarize / architecture (Claude)
    → Human interview in the main chat
    → AI writes fourteen docs under docs/
    → CLI gates + certification verify
```

### 5.3 Steps

**Step 1 — Deterministic Stage 0 with docs intended in the target repo**

```bash
doc-engine pipeline run <repo_path> \
  --compliance-profile deterministic_only \
  --out-dir <run_dir> \
  --docs-in-target-repo
```

`--docs-in-target-repo` tells the run that documentation will live under the target’s `docs/` folder (important for later gates).

**Step 2 — Run the generative skill in Claude**

In Claude Code, with the plugin/adapter loaded, ask to document the Spring Boot repository (skill name: `document-spring-repo`). Point it at the same `<repo_path>` and `<run_dir>` you used above.

Follow the skill’s instructions for agent fan-out. **Do not invent your own stage order** — use the skill.

**Step 3 — Interview**

When asked clarifying questions (who calls this API, write ownership of a table, known limitations, and similar):

- Answer with what you know (`answered`).
- Or skip (`skipped`) when nobody knows — that is honest and expected.
- Answers are stored as `interview_answers.json` in the run directory.

**Step 4 — Confirm the fourteen files**

Under `<repo_path>/docs/` you should get (names may be lowercase as produced by the writer):

`readme.md`, `architecture.md`, `integrations.md`, `authorization.md`, `database.md`, `operations.md`, `observability.md`, `troubleshooting.md`, `configuration.md`, `change_impact.md`, `glossary.md`, `local_development.md`, `testing.md`, `known_limitations.md`.

Details of what each file must cover: [`adapters/claude/skills/document-spring-repo/references/doc-taxonomy.md`](../../adapters/claude/skills/document-spring-repo/references/doc-taxonomy.md).

The tool must **not** overwrite a root `README.md` if one already exists — onboarding overview goes to `docs/readme.md` in that case.

**Step 5 — Gates and certification**

```bash
doc-engine pipeline gates \
  --out-dir <run_dir> \
  --target-repo <repo_path> \
  --docs-dir <repo_path>/docs

doc-engine certification verify <run_dir>/certification.json
```

Do **not** tell anyone the run “succeeded” if gates fail.

### 5.4 How to read claim tags in the docs

Generated prose should tag claims roughly as:

| Tag | Meaning |
|-----|---------|
| **`[Evidenced — …]`** | Supported by a code citation (path/line or equivalent). |
| **`[Confirmed — …]`** | Backed by an interview answer. |
| **`[Unknown — …]`** | Could not be evidenced or confirmed. |

**`[Unknown]` is success of honesty, not failure of the tool.** A doc full of invented certainty would be worse.

### 5.5 Path B success criteria

- Fourteen files present under the target `docs/` (or documented intentional skips).
- `doc-engine pipeline gates` exits successfully.
- `doc-engine certification verify` exits 0.
- You personally reviewed Unknowns and anything near `redaction_zones` / configuration.

**Important:** `certified: true` with `generative_executor: mock` only proves **structural** wiring. Live Path B prose quality still needs a human (and optionally the semantic eval skill below).

---

## 6. After the run

### What to keep vs commit

| Location | Typical policy |
|----------|----------------|
| Target `docs/*.md` | Commit to the *service* repo after review. |
| `<run_dir>` JSON / certification | Keep for audit; often **do not** commit huge run dirs unless your team agrees. |
| Product repo | You do not need to change this product repo to document a service. |

### Optional: drift check later

After the service changes, compare a saved `spring_signals.json` to the current tree:

```bash
python -m doc_engine.tools.spring_drift_check <repo_path> <run_dir>/spring_signals.json --out drift_report.json
```

Use the report to decide whether to re-run Stage 0 (and Path B).

### Optional: semantic evaluation (manual)

After a completed live Path B run, follow [`adapters/claude/skills/semantic-pipeline-eval/SKILL.md`](../../adapters/claude/skills/semantic-pipeline-eval/SKILL.md) with `PIPELINE_ARTIFACTS_DIR` set to `<run_dir>`. A human should review escalated findings. This is not automatic CI.

### Optional org hardening checklist

Repo-admin / multi-team steps (branch protection on *this* product, capacity on largest service, etc.): [`docs/adoption-hardening.md`](../adoption-hardening.md).

---

## 7. Troubleshooting

| Problem | What to check |
|---------|----------------|
| `doc-engine` not found | `pip install -e .` from the product repo; new terminal; `where doc-engine` / `which doc-engine`. |
| Wrong `ast-grep` version | PATH shadowing; see tool-quirks; prefer `requirements.txt` pin. |
| Empty or tiny signals | Wrong root folder; not Spring Boot; scan exclusions. |
| Gates fail after Path B | Docs not under expected `docs/`; missing files; stray writes; re-read gate error text. |
| Certification says certified but docs look thin | Mock generative executor or incomplete live stages — re-read §5.5. |
| Confused by two `skills/` trees | Product SoT is `adapters/claude/skills/`; root `skills/` is a mirror. |
| “This guide ≠ what Claude did” | Follow the skill / CLI; update assumptions from [`STATUS.md`](../../STATUS.md). |

---

## Quick command cheat sheet

```bash
# Install (product repo)
pip install -r requirements.txt && pip install -e .

# Path A
doc-engine pipeline run <repo_path> --compliance-profile deterministic_only --out-dir <run_dir>

# Path B Stage 0 (then Claude skill + interview)
doc-engine pipeline run <repo_path> --compliance-profile deterministic_only --out-dir <run_dir> --docs-in-target-repo

# Path B finish
doc-engine pipeline gates --out-dir <run_dir> --target-repo <repo_path> --docs-dir <repo_path>/docs
doc-engine certification verify <run_dir>/certification.json
```
