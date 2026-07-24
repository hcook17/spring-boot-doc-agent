# Tool and environment quirks

Append-only index of odd behavior in the *ambient tools/environment* used to work on this repo (`gh`, `git`, MCP tools, the shell, Windows-specific path handling) — not this plugin's own document-generation logic. See `skills/tool-quirks/SKILL.md` for when to check this before investigating, and when/how to add an entry. Distinct from `claude/session-log.md` (steering-prompt impact) and `claude/llms/` (this repo's own PR-verification commands).

Newest entries at the bottom.

---

## 2026-07-24 — `gh pr create` produced a PR with a truncated title and the raw commit message as its body, instead of the passed `--title`/`--body`
Tools/commands involved: `gh` CLI 2.96.0, non-TTY Git Bash (`tty` reports "not a tty"), `git push -u origin <branch>` immediately followed by `gh pr create --title ... --body "$(cat <<'EOF' ... EOF)"`
Status: [Unresolved — needs research]
Symptom: after `git push -u origin add-semantic-eval-and-capacity-preflight` (which only printed GitHub's standard "create a pull request by visiting: <url>" hint, not an actual creation), a subsequent `gh pr create --title "..." --body "..."` call failed with "a pull request... already exists," pointing at PR #13. `gh pr view 13 --json title,body` showed a title truncated mid-word with a real ellipsis character (`"...matu…"`, not a display artifact) and a body that was just the raw multi-line commit message — neither matched the `--title`/`--body` content that had been passed to any command actually run in this session.
Diagnostic steps taken (re-runnable):
    ls -la .git/hooks | grep -v sample          # no non-sample local hooks
    git config --list --local                   # no custom hooks/push config
    git config --global --list | grep -i "hook\|push\|pr\b"
    git config --global core.hooksPath           # unset
    gh config list                               # no auto-PR-related settings
    gh alias list                                 # only a `co` alias, unrelated
    gh api repos/<owner>/<repo>/hooks             # []  — no repo webhooks
    gh api repos/<owner>/<repo>/installations     # 404 — no GitHub Apps installed
    gh --version                                  # 2.96.0
    tty                                            # "not a tty"
    gh pr list --state merged --limit 5 --json number,title   # PRs #8-#12 in this same repo all have full, correct titles — no truncation, no commit-message-fallback pattern
Resolution / workaround: fixed the immediate symptom directly — `gh pr edit <number> --title "..." --body "..."` — reconciles the PR's actual stored title/body with what was intended; verified with a follow-up `gh pr view --json title,body` read rather than trusting the edit command's exit code (the specific write-then-verify step that would have caught this originating problem earlier too). Root cause still not identified: no local/global git hooks, no repo webhooks, and no installed GitHub Apps account for it, and the same non-TTY environment produced correctly-titled/bodied PRs in this repo's own prior history (#8-#12), so it isn't simply "this environment always does this." Treat as a one-off until it recurs — if it does, the next occurrence should re-run the checklist above first and add whatever it finds to this entry rather than starting over.

---

## 2026-07-24 — A read-only (no git/gh access) session reviewing a PR via GitHub's web UI got an incompletely-loaded diff, and nearly reported the PR as reviewed anyway
Tools/commands involved: GitHub web UI "Files changed" tab, a plain HTTP fetch tool (no JS execution), the `.diff`/`.patch` endpoints, a commit page
Status: [Resolved — workaround identified, and a repo-level mitigation exists]
Symptom: a Cowork session (no git/gh access — it can only fetch web pages) tried to review PR #13 by fetching its "Files changed" page. That page renders diffs progressively via JavaScript; a plain fetch only gets whatever HTML shell loaded before JS populated the diff hunks. 4 of 12 changed files loaded fully; the other 8 (including the two files most load-bearing for the review) showed unresolved "Loading…" placeholders. The `.diff` endpoint and the commit page were tried as fallbacks and both got blocked (permissions/robots-style rejection on unauthenticated scraping of those specific paths). The session correctly refused to claim the PR was verified off an incomplete page rather than silently treating a partial load as a full one.
Diagnostic steps taken (re-runnable): none needed beyond noticing the "Loading…" placeholders and the blocked fallback endpoints — the fix here is a different request shape, not further diagnosis.
Resolution / workaround: two complementary fixes, neither requiring new tooling:
1. **For any file's full content or diff, use GitHub's REST API instead of the web UI** — plain JSON/text over HTTP, not JS-rendered, so a basic fetch gets the complete content in one shot:
   - `https://api.github.com/repos/<owner>/<repo>/pulls/<N>/files?per_page=100` — full unified diff (`patch` field) per changed file, plus additions/deletions/status.
   - `https://raw.githubusercontent.com/<owner>/<repo>/<branch-or-sha>/<path>` — full raw file content, for anything whose `patch` is large/omitted by the API too.
2. **This repo's own `claude/llms/pr-N.md` convention can be written for a still-open PR, not just a merged one** — confirmed directly against `scripts/verify_llms_docs.py` (its parser is agnostic to merge state; it just scans for backtick-fenced `git`/`gh` commands and runs them against whatever ref is embedded) and `claude/llms/README.md` (which already names "a still-open PR, pinned to its head branch" as a supported case). Since the resulting file is a single plain-markdown file, it's *also* fetchable via `raw.githubusercontent.com` without hitting any JS rendering — writing one for an in-flight PR gives a read-only session a complete, curated, non-paginated summary instead of the diff UI, on top of (not instead of) fix 1 above.

---

## 2026-07-24 — `gh api repos/.../pulls/<N>` returns a stale `.head.sha` after a fast push, even though the branch ref itself updated correctly
Tools/commands involved: `gh` CLI 2.96.0, `gh api repos/<owner>/<repo>/pulls/<N>`, `gh api repos/<owner>/<repo>/compare/<base>...<branch>`, `git ls-remote`
Status: [Diagnosed — root cause identified, workaround confirmed]
Symptom: after `git push` reported success (`13553ba..b4b23d3 add-semantic-eval-and-capacity-preflight -> add-semantic-eval-and-capacity-preflight`), both `gh pr view 13 --json commits` and `gh api repos/<owner>/<repo>/pulls/13 --jq '.head.sha'` kept reporting the *previous* commit (`13553ba`) as the PR's head for well over 30 seconds afterward (checked immediately, again after 5s, again after 30s, with a `Cache-Control: no-cache` header on one attempt — all stale). This came right after two earlier pushes to the same PR in the same session where the exact same check had updated correctly within a second or two of pushing, so it wasn't simply "this always lags."
Diagnostic steps taken (re-runnable):
    git ls-remote <repo-url> refs/heads/<branch>                              # ground truth: correctly showed the new commit immediately
    gh api repos/<owner>/<repo>/pulls/<N> --jq '.head.sha'                    # stale — kept the prior commit
    gh api repos/<owner>/<repo>/pulls/<N>/commits --jq '[.[].sha]'            # also stale — only listed the prior commits
    gh api repos/<owner>/<repo>/compare/<base>...<branch> --jq '.commits[].sha'  # correct — showed the new commit immediately
Resolution / workaround: the `pulls/{number}` endpoint's `head.sha`/`commits` fields specifically can lag behind the actual branch ref after a fast push — this is a read-side propagation/caching quirk on GitHub's `pulls` API object, not a failed push and not something wrong with the branch itself. When you need to confirm "did my push actually land" and the `pulls` endpoint looks stale, cross-check against `git ls-remote <url> refs/heads/<branch>` (ground truth) or `gh api repos/.../compare/<base>...<branch>` (also correct, and gives the full commit list) rather than concluding the push failed or retrying it. Root cause (why `pulls` specifically lags while `compare`/`ls-remote` don't) not identified — GitHub's own internals, not something diagnosable from this side. Not confirmed as a persistent pattern; if `pulls`'s `head.sha` lags again after a future push in this repo, note how long it took to catch up here to build a real time-bound expectation.

---

## 2026-07-24 — Continued pushing commits to a PR branch after the PR had already merged; those commits went into the void, not into main
Tools/commands involved: `git push`, `gh pr create`/`gh pr view`, GitHub's own PR-merge semantics
Status: [Resolved — recovered via cherry-pick, new PR opened; process gap identified]
Symptom: PR #13 merged into `main` at commit `13553ba`. Two more commits (`b4b23d3`, `3d6e1d6`) were pushed to that same branch afterward, in the same working session, without checking whether the PR was still open. Both pushes reported success, and `git ls-remote`/`git fetch` correctly showed the branch's tip advancing each time — but none of that indicates whether the *PR* is still open to receive those commits. Since PR #13 was already `MERGED`, pushing more commits to its branch does not reopen the PR or add anything to `main` — they just sit on an orphaned branch, invisible unless something explicitly checks `git merge-base --is-ancestor <commit> origin/main`. The gap was only caught because the user noticed the GitHub UI/`gh pr view` weren't reflecting the latest push (which led into the separate `pulls`-endpoint staleness quirk logged above) — investigating *that* is what surfaced the real problem underneath it.
Diagnostic steps taken (re-runnable):
    gh pr view <N> --json state,mergedAt,mergeCommit --jq '{state, mergedAt, mergeCommit: .mergeCommit.oid}'   # confirms MERGED and the exact commit it merged at
    git log --pretty="%H %P" -1 <merge_commit_sha>              # merge commit's second parent = the branch tip that actually got merged
    git merge-base --is-ancestor <commit> origin/main && echo "in main" || echo "NOT in main"   # the actual check that should run before/after any push to a PR branch
    # Repo-wide sweep for the same pattern across every branch:
    git ls-remote --heads origin
    gh pr list --state merged --limit 50 --json number,headRefName,mergeCommit
    for b in <every still-existing branch>; do git merge-base --is-ancestor origin/$b origin/main || echo "$b: NOT in main"; done
Resolution / workaround: recovered by cherry-picking the two stranded commits onto a fresh branch off current `main` and opening a new PR (#14), rather than trying to reuse or reopen the merged one. The repo-wide sweep above found no other instance of this pattern in this repo's history — isolated to PR #13. **The actual process fix, not just this incident's recovery**: before pushing another commit to an existing PR branch, check `gh pr view <N> --json state` (or `git merge-base --is-ancestor origin/main <branch-tip>` in the other direction — is the branch's base still where you think it is) first — don't assume a branch you were just working on is still an open target just because the local checkout/tracking state looks unchanged.

---

## 2026-07-25 — Two separate `ast-grep` installs on the same Windows dev machine silently shadow each other on `PATH`, so a pip-side version bump doesn't change what `ast-grep --version` reports
Tools/commands involved: `pip install ast-grep-cli`, `shutil.which("ast-grep")` (used by `scripts/spring_signal_scan.py`'s `find_ast_grep()`), Git Bash `PATH` on Windows
Status: [Resolved — understood, not a bug in this repo's own code]
Symptom: while pinning dependencies (`requirements.txt`, `ast-grep-cli~=0.45.0`) and re-running `pip install -r requirements.txt`, pip correctly reported upgrading `ast-grep-cli` from `0.44.1` to `0.45.0` — but a subsequent `ast-grep --version` on the same shell still printed `0.44.1`. `pip show -f ast-grep-cli` showed the pip-managed script living at `...AppData\Roaming\Python\Python314\Scripts\ast-grep.exe`, while `shutil.which("ast-grep")` (and Git Bash's own `which`) resolved to a *different* binary at `C:\Users\16145\bin\ast-grep.EXE` — an separately-installed copy (this machine also has `cargo install ast-grep` / `npm install -g @ast-grep/cli` conventions documented in `README.md`/`CONSTRAINTS.md` item 1, and one of those installed here earlier, ahead of the pip Scripts dir on `PATH`).
Diagnostic steps taken (re-runnable):
    pip show -f ast-grep-cli | grep -i "location\|Files" -A3    # shows the pip-managed script's actual path
    which -a ast-grep                                            # lists every ast-grep on PATH, in resolution order
    python3 -c "import shutil; print(shutil.which('ast-grep'))"  # confirms which one Python code (spring_signal_scan.py) actually shells out to
Resolution / workaround: not a repo bug — `spring_signal_scan.py`'s `find_ast_grep()` correctly uses whatever `ast-grep` resolves to first on `PATH`, and this repo's pinning task only ever targeted the pip-packaged `ast-grep-cli` wrapper (`CONSTRAINTS.md` item 1 explicitly says not to touch the cargo/npm binary install path). To actually exercise the pinned pip version locally, prepend the venv/site's `Scripts` (or `bin`) directory to `PATH` ahead of any other `ast-grep` install, e.g. `export PATH="<venv>/Scripts:$PATH"`, and re-verify with `which -a ast-grep` before trusting a version-pinning test result. A genuine CI runner (no pre-existing cargo/npm `ast-grep` on the image) won't hit this at all — it's a local-multi-install artifact, not a production concern — but worth checking `which -a ast-grep` first on any machine with more than one `ast-grep` install history before concluding a pin "didn't take."
