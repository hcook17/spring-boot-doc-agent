# Working conventions for this repo

## Steering prompts and the session log

`claude/steering-prompts/` contains <!-- derived: steering_prompt_count -->14<!-- /derived --> numbered prompts. **`00`–`06` are mirrored from this project's attached Claude project ("Plugin For Asynchronous Documentation Creation") and have a canonical copy there; `07` and up were authored in this repo and exist nowhere else** (confirmed 2026-07-24 — the project's folder holds `00`–`06` only). Edits to `00`–`06` need mirroring back; edits to `07` and up do not. They fall into three groups:

- **`00`–`05` — research/scaffold prompts.** `00` shared standards, then one per improvement category: testability, pluggability, constraints, analytics-logging, clarity/delivery-trust.
- **`06`–`09` — implementation task prompts.** Wire drift-check, CI scaffold, dependency pinning, tool-quirks indexing. These carry a `status:` frontmatter field that is edited in place as the task lands; the body is left as historical record rather than rewritten.
- **`10`–`12` — the review layer.** Review persona and evidence tiers, the DFS/BFS context-traversal protocol, and the paste-able review-session launcher. Read these when the session is a review or a design-weighing pass rather than a build.
- **`13` and up — research prompts authored after the three groups above were named.** `13` is code quality/expressiveness. Numbered ranges in this file are the kind of claim that goes stale the moment a prompt is added, which is why the count above is a `derived:` block and these ranges are open-ended.

Each prompt states specific factual assumptions about the current state of this repo (e.g., "no test exists for the LLM stages," "the confidentiality rule only lives in a handoff doc"). Commits to this repo can make those assumptions stale.

**Every prompt carrying a `status:` also carries a `verify:` list** — decidable predicates that `scripts/check_repo_claims.py` evaluates on every CI run, so a status contradicting the repo fails the build instead of waiting to be noticed:

```
status: resolved (2026-07-23, PR #3)
verify:
  - contains:skills/document-spring-repo/SKILL.md:spring_drift_check.py
  - contains:README.md:spring_drift_check.py
```

<!-- derived: predicate_count -->5<!-- /derived --> forms, and no others: `path_exists:<path>`, `path_absent:<path>`, `contains:<path>:<literal>`, `not_contains:<path>:<literal>`, `unchanged_since:<path>:<level>:<digest>`. An unrecognized predicate fails rather than being skipped. (This sentence read "Three forms" for two separate windows after a fourth and then a fifth landed — hence the derived block. `PREDICATE_PREFIXES` was already derived from the registry in one direction; this closes the other.) Write them to falsify the status in the direction that actually bites — a `not started` prompt should assert its deliverable is **absent**, which is the exact shape `06` got wrong. That prompt's `status:` read `not started` for a whole window after the work landed and was flagged three separate times in `claude/session-log.md` before anyone edited the field; its own `note:` records this. A predicate would have failed the build the first time.

`07`'s `path_absent:scripts/verify_llms_docs.py` is worth understanding as a pattern: it turns "deleted as a security defect — do not re-add it" from a comment into a build failure.

**Before your final commit in any session that touches `scripts/`, `agents/`, or `skills/`:** run `python3 scripts/check_repo_claims.py` first — it mechanically resolves every prompt's `verify:` predicates, every `derived:` count, and every backticked repo path in the current-state docs, which is the part of this pass that used to depend on someone remembering. Then read the prompt files and check whether anything you just changed resolves, contradicts, or otherwise affects a stated assumption in any of them. In practice `00`–`09` and `13` carry repo-state assumptions; `10`–`12` describe method and rarely go stale from a code change.

The checker is the floor, not the ceiling: it decides whether a claim is *well-formed and resolvable*, never whether it is *true*. A `[Resolved]` tag pointing at a file that exists still passes while being wrong about what the file does. That judgment is what the rest of this pass is for. See `.claude/skills/verify-state-claims/SKILL.md`.

- If nothing you changed is plausibly relevant to any of the prompts, don't write a log entry — churn here is worse than silence. Most commits (a typo fix, a small test addition) won't touch anything a steering prompt assumed.
- If something is relevant, append one entry to `claude/session-log.md` (create it from the template below if it doesn't exist yet) in the same commit. Keep it distilled, not a raw diff — the point is that a downstream reviewer (human or another Claude session) can read ten lines instead of parsing a diff.

### The same check covers `CONSTRAINTS.md`

`CONSTRAINTS.md`'s `[Resolved]` / `[Partially resolved]` / `[Flagged, not yet resolved]` entries make the same kind of statement a steering prompt does — a claim about this repo's current state that a later commit can falsify — so check them in the same pass, on the same trigger (`scripts/`, `agents/`, `skills/`). `check_repo_claims.py` covers the mechanical half: a `CONSTRAINTS.md` entry citing a path or `symbol()` that no longer exists now fails CI, which is how this file managed to cite a deleted script in two places at once. What it cannot decide is whether a surviving path still supports the claim attached to it, so this pass remains the only thing standing between *that* and silent drift. Three things worth knowing:

- **Correct the entry in place.** `CONSTRAINTS.md` is a current-state doc, not an append-only log — fix the claim where it stands, keeping the bracket-tag vocabulary above. Only add a `claude/session-log.md` entry if a steering-prompt assumption moved too; a `CONSTRAINTS.md` correction on its own isn't log-worthy.
- **A claim can drift in either direction.** It can become false, or it can have been written *ahead of* the code and only become true later — a `[Resolved]` written for a fix that was still partial reads as settled when it isn't. Both are worth correcting, and say which happened rather than quietly restating the claim.
- **Don't hardcode a count.** They go stale faster than they get read, and this bullet is the proof: it used to carry three wrong numbers of its own, quoting a `MATURITY_ASSESSMENT.md` sentence that had already been corrected and stamping its replacement "as of" a date it was wrong on. Two fixes, in order of preference. Name the command that recomputes it, which `MATURITY_ASSESSMENT.md` and `CONSTRAINTS.md`'s drift-check entry both now do. Or, when a number genuinely has to appear in prose, wrap it in a derived block:

    ```
    the workflow runs <!-- derived: ci_test_steps -->N<!-- /derived --> suites
    ```

  `scripts/check_repo_claims.py` recomputes each one and fails CI on a mismatch; `--fix` rewrites them. Add the key to that script's `DERIVATIONS` dict first — markdown can only *select* a derivation, never define one, which is what keeps this from becoming the markdown-to-shell hazard that got `verify_llms_docs.py` deleted. Blocks inside a fenced example, like the one above, are ignored.

### Entry format

```
## <YYYY-MM-DD> — <short description of the commit>
Commit: <short sha, or "uncommitted" if writing before commit>
Tests: <pass/fail summary if you ran the relevant suite, e.g. "18/18 passing", or "not run">
Assumptions affected:
- `<prompt file>` — "<short quote or paraphrase of the specific assumption>" — [Resolved — <what changed, in this commit>] / [Still accurate] / [New info — <what changed and why the prompt may need editing>]
Files touched: <comma-separated list>
```

Reuse the bracket-tag convention already established elsewhere in this project (`Evidenced` / `Confirmed` / `Unknown` in the doc-writer output) rather than inventing new status words — `[Resolved — ...]`, `[Still accurate]`, and `[New info — ...]` are the three states that matter here; don't add more without a real reason to.

Only tag an assumption `[Resolved]` if you're confident the prompt's stated problem no longer exists after your change — not just that you touched the same file. If you're not sure whether an assumption is now stale, say so explicitly (`[New info — unsure if this is still accurate, needs a look]`) rather than guessing either direction.

### Why this exists, not just what to do

A Claude Code CLI session (this one) has full repo and git access but no access to the Claude project where the canonical copies of `00`–`06` live. A Cowork session attached to that project has the reverse — it can read/edit the prompts but can't run git commands against this repo directly. `claude/session-log.md` is the one file that crosses that gap: cheap for this session to write (it already has full context of its own change), and small enough for the other session to read directly once it has folder access, without needing the full diff or `.git` history relayed by hand.

## Searching code: ast-grep, never text search

**Agents search structurally.** No agent definition may declare the `Grep` tool, and `grep`/`rg` are denied through `Bash` in `.claude/settings.json`. `scripts/check_repo_claims.py`'s check F fails the build if an agent regains `Grep`, and `hooks/deny_text_search.py` (a `PreToolUse` hook, shipped in `hooks/hooks.json` and verified to fire for subagents as well as the main thread) blocks it at runtime. Two controls because they fail differently: the static one cannot be bypassed but only runs in CI; the runtime one catches an agent shelling out to `grep` through `Bash`, which static inspection cannot see.

The reason is citation correctness, not taste. Text search matches inside strings and comments, which is how a claim ends up carrying an `[Evidenced — path:line]` tag anchored to a line that does not support it.

Each of the following has produced a wrong answer here, in this repo, and is worth reading before writing a pattern (no count, deliberately — the list grows, and the sentence that used to carry one was wrong within a day of being written):

- **A marker annotation and an argument-bearing annotation are disjoint node shapes.** `-p '@Column'` returns **zero** against a file holding 122 `@Column(name = "...")`. Always try `@Name` *and* `@Name($$$)`. Every rule in `spring_ast_grep_rules.yml` that can take arguments lists both forms for this reason.
- **A zero result means *unproven*, not *absent*.** ast-grep exits 0 when a structurally valid pattern matches nothing, so a silent zero is indistinguishable from a wrong pattern. Never turn one into a claim that something is not there.
- **The mandate binds where ast-grep has a grammar.** It has none for Groovy (`-l groovy` fails outright), so Gradle build scripts are classified by filename in `spring_signal_scan.py` and carry no structural signals at all. Kotlin and Scala it does support. Check before designing around a language: `echo x | ast-grep run --stdin -l <lang> -p x`.
- **ast-grep is not a prose search tool.** Its `markdown` grammar matches broad block nodes: on `README.md`, `-p 'ast-grep'` reports 35 lines of which 27 contain no such string. For docs and logs, use `Glob` to narrow and `Read` to open. The mandate is about *code*, where citations live.

**Coverage is the invariant the mandate exists to serve**, and it is enforced separately. `scripts/rule_coverage.py` runs the <!-- derived: ast_grep_rule_count -->29<!-- /derived --> rules against the committed corpus in `scripts/rule_fixtures/` and fails if any rule matches nothing — a rule nobody can make fire is not coverage. It also has a backtest mode against a real repository, ratcheted against `scripts/rule_coverage_baseline.json`; that corpus is far too large to track, so it is measured on a dev machine and only the baseline is committed. Adding a rule means adding a fixture that triggers it, in the same commit.

## Tool and environment quirks

`claude/tool-quirks.md` is a separate, append-only index from `claude/session-log.md` above — it's about odd behavior in the *ambient tools/environment* this repo is worked in (`gh`, `git`, MCP tools, Windows/Git-Bash-specific quirks), not this plugin's own document-generation logic. See `skills/tool-quirks/SKILL.md` for the full convention. Check it before deep-diving into something that looks like a tool bug; append an entry whenever you diagnose one (resolved, partially diagnosed, or still open) so the next session doesn't redo the investigation.
