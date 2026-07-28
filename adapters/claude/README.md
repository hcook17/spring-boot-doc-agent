# Claude Code adapter

Optional distribution pack for Claude Code. The **product** is the `doc-engine` Python package; this folder is what the marketplace installs as `CLAUDE_PLUGIN_ROOT`.

## Install

From the repository root:

```bash
claude plugin marketplace add ./spring-boot-doc-agent
claude plugin install spring-boot-doc-agent@spring-boot-doc-agent-marketplace
```

Marketplace entry points `source` at this directory (`adapters/claude`).

## Contents

| Contents | Role |
|------|------|
| `agents/` | Subagent prompts (Task fan-out for generative stages) |
| `hooks/` | PreToolUse hooks (text-search and network egress deny) |
| `skills/` | Claude skills including `document-spring-repo` |
| `SEARCH.md` | Agent search playbook (ast-grep vs grep — runtime scope) |
| `plugin.json` | Plugin metadata |

For deterministic / CI work, prefer `doc-engine pipeline run` over SKILL bash sequences. Use the SKILL for live generative stages and the interview.
