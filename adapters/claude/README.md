# Claude Code adapter

Optional distribution pack for Claude Code. The **product** is the `doc-engine`
Python package; this folder is what the marketplace installs as
`CLAUDE_PLUGIN_ROOT`.

## Architecture lock (A+C hybrid)

| Layer | Owns |
|-------|------|
| `doc-engine` (pip) | Stage graph (`build_stage_specs()`), Stage 0, gates, certification |
| This adapter | Skills, agents, hooks, SEARCH.md, short CONSTRAINTS stub |

Skills **must not** invoke deterministic tools via a plugin-local `scripts/`
tree — that path does not exist after marketplace install (plugin is copied to
Claude’s cache without the monorepo `scripts/` directory). Deterministic work
goes through the CLI only.

## Install

```bash
pip install -e .   # from the spring-boot-doc-agent repo root (required)
claude plugin marketplace add ./spring-boot-doc-agent
claude plugin install spring-boot-doc-agent@spring-boot-doc-agent-marketplace
```

Marketplace `source` is this directory (`adapters/claude`).

## Contents

| Contents | Role |
|----------|------|
| `agents/` | Subagent prompts (Task fan-out for generative stages) |
| `hooks/` | PreToolUse hooks (text-search and network egress deny) |
| `skills/` | Claude skills including `document-spring-repo` |
| `CONSTRAINTS.md` | Short runtime prerequisites (plugin-local) |
| `SEARCH.md` | Agent search playbook |
| `plugin.json` | Plugin metadata |

## Operator commands

```bash
# Stage 0 only (then run generative stages via the skill)
doc-engine pipeline run /path/to/spring-repo \
  --compliance-profile deterministic_only \
  --out-dir /tmp/doc-run \
  --docs-in-target-repo

# Step-through (stage names from build_stage_specs())
doc-engine pipeline run /path/to/spring-repo --until partition --out-dir /tmp/doc-run

# After live agents write docs/
doc-engine pipeline gates --out-dir /tmp/doc-run --target-repo /path/to/spring-repo --docs-dir /path/to/spring-repo/docs

doc-engine certification verify /tmp/doc-run/certification.json
```

Full mock E2E (CI): `doc-engine pipeline run` with default/certified profile.
