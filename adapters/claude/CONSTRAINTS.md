# Claude adapter runtime prerequisites

This file lives under the Claude plugin root (`CLAUDE_PLUGIN_ROOT`) so marketplace
installs can resolve `${CLAUDE_PLUGIN_ROOT}/CONSTRAINTS.md`.

It is a **short stub**, not a second copy of the monorepo
[`CONSTRAINTS.md`](../../CONSTRAINTS.md). Full precision tradeoffs, enterprise
gaps, and resolved claims live in that repo-root document when you have the
source checkout.

## Hard prerequisites (A+C hybrid)

1. **Install the product package** (deterministic tools are *not* shipped inside this plugin):

   ```bash
   pip install -e /path/to/spring-boot-doc-agent
   # or: pip install doc-engine   # when published
   ```

   Confirm: `doc-engine --help` and `doc-engine pipeline run --help`.

2. **`ast-grep` on `PATH`** for Stage 0 signal scan (pinned via `requirements.txt` /
   `ast-grep-cli` in the product repo).

3. Optional: **CodeQL** / **semgrep** when using those scanners or the
   architecture/testing agent — see the monorepo CONSTRAINTS for details.

## What this plugin contains

| Path | Role |
|------|------|
| `skills/` | Generative orchestration (interview + Task fan-out) |
| `agents/` | Subagent prompts |
| `hooks/` | PreToolUse denials (text search / raw network) |
| `SEARCH.md` | ast-grep citation discipline |

Deterministic Stage 0, gates, and certification live in the **`doc-engine` CLI**,
not under a plugin-local `scripts/` tree (marketplace installs must not ship one).

## Invoke surface (allowlist)

```bash
doc-engine pipeline run <repo> --compliance-profile deterministic_only --out-dir <run>
doc-engine pipeline run <repo> --until partition --out-dir <run>
doc-engine pipeline gates --out-dir <run> --target-repo <repo> --docs-dir <docs>
doc-engine certification verify <run>/certification.json
```

See [`README.md`](README.md) and [`docs/product-architecture.md`](../../docs/product-architecture.md).
