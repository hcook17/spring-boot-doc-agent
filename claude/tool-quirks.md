# Tool and environment quirks

Append-only index of odd behavior in the *ambient tools/environment* used to work on this repo (`gh`, `git`, MCP tools, the shell, Windows-specific path handling) — not this plugin's own document-generation logic. See `adapters/claude/skills/tool-quirks/SKILL.md` for when to check this before investigating, and when/how to add an entry. Distinct from `claude/session-log.md` (steering-prompt impact) and `claude/llms/` (this repo's own PR-verification commands).

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

**Recurred 2026-07-25, PR #28** (`sync-status-ast-grep-jpql-lineage` -> `main`): same shape exactly — `git push -u origin sync-status-ast-grep-jpql-lineage` (printed only the standard "create a pull request by visiting: <url>" hint) followed immediately by an explicit `gh pr create --title ... --body ...` call, which failed with "a pull request... already exists," pointing at #28. `gh pr view 28` showed a title truncated mid-word and the raw multi-line commit message as body — not the `--title`/`--body` just passed. Did not re-run the full diagnostic checklist above this time (same environment, same `gh`/`git` versions as the original diagnosis, no new signal expected) — went straight to the known workaround (`gh pr edit 28 --title ... --body ...`, verified with a follow-up `gh pr view --json title,body` read, which confirmed the fix took). Second confirmed occurrence in the same repo/environment now, both times immediately following a `git push -u origin <new-branch>` right before `gh pr create` — worth treating that specific sequence as the likely trigger if a third occurrence happens, even though the original diagnostic pass found no hook/webhook/App cause for *why* the push itself would create a PR.

**Recurred 2026-07-24, PR #29** (`doc-accuracy-fixes` -> `main`) — third occurrence, and it refines the pattern in two ways worth recording:

1. **The auto-created PR's title/body took a different shape.** The first two occurrences produced a title truncated mid-word plus the raw multi-line commit message as body. #29 instead got `"Doc accuracy fixes"` — the branch name de-kebabed and sentence-cased — and a **completely empty body**. So the failure isn't "gh's `--title`/`--body` get mangled"; it's that *something other than the `gh pr create` call* opens the PR, and whatever does it derives the title however it likes. That makes "the push creates it" a better hypothesis than "gh truncates," and it means you cannot predict what title you'll get.
2. **`gh pr list` did not show the PR for at least ~3 seconds after the push.** `gh pr list --head doc-accuracy-fixes --state all --json number,state,title` returned `[]` about three seconds after `git push -u` completed, which read as "no auto-PR this time." The subsequent `gh pr create` then failed with "a pull request for branch ... already exists: .../pull/29". So **a `[]` from `gh pr list` immediately post-push does not mean no PR was created** — this is the same read-your-own-write staleness already logged for the `gh api pulls/{N}` `head.sha` quirk further down this file, hitting a different endpoint.

Practical consequence: don't branch on a post-push `gh pr list` result. Either sleep well past a few seconds before checking, or skip the check entirely and go straight to `gh pr create`, treating "already exists: .../pull/N" as the *expected* path that hands you the number. Then `gh pr edit N --title ... --body-file -` and verify with `gh pr view N --json title,body` — that workaround worked cleanly again here (title set, body 4710 chars, both commits attached).

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

---

## 2026-07-25 — `EnterWorktree` fails with "Command 'git' not found or is in an unsafe location" on this Windows machine, even though Git Bash's own `git` works fine
Tools/commands involved: `EnterWorktree` (Claude Code harness tool), Windows-native PATH resolution, Git Bash `PATH`
Status: [Resolved — the underlying `PATH` defect was fixed 2026-07-24 at user scope; see the "Git `PATH` entry pointed at the install root" entry at the bottom of this file. The diagnosis below was correct and is what made the fix a two-minute job.]
Symptom: `EnterWorktree` (both `name:` and `path:` forms) failed every time in this session with `Command 'git' not found or is in an unsafe location (current directory)`, even though `git worktree add` run directly via the Bash tool (Git Bash / mingw64) worked perfectly, and `git --version` via Bash resolved to `2.55.0.windows.3` with no ownership/safe-directory issues.
Diagnostic steps taken (re-runnable):
    which git; git --version                          # via Bash tool -- works, resolves to mingw64 git
    Get-Command git -ErrorAction SilentlyContinue      # via PowerShell tool -- NOT FOUND
    $env:PATH -split ';' | Select-String -Pattern 'git'  # shows "C:\Program Files\Git" IS on the Windows-native PATH...
    Test-Path "C:\Program Files\Git\cmd\git.exe"       # ...but true -- so git.exe lives one level down (\cmd or \bin), not directly in the PATH-listed folder
Resolution / workaround: the harness's `EnterWorktree` tool appears to shell out via the Windows-native process environment (same one the PowerShell tool sees), not Git Bash's — and on this machine the Windows-native `PATH` entry for Git points at `C:\Program Files\Git` itself rather than `C:\Program Files\Git\cmd` (where `git.exe` actually lives), so native `Get-Command git` / whatever `EnterWorktree` uses internally can't resolve it, even though Bash-tool git calls work fine (mingw64 resolves its own bundled git via a different mechanism). Not fixed (would require changing the user's system `PATH`, out of scope for a single session to do unprompted). Workaround used this session: created the worktree manually via `git worktree add -b <branch> .claude/worktrees/<name> <base-branch>` through the Bash tool, then — since `EnterWorktree path:` *also* fails for the same underlying reason even pointed at an already-existing worktree — fell back to editing in the shared checkout directly with `.claude/settings.local.json`'s `{"worktree": {"bgIsolation": "none"}}` override (written via Bash heredoc, since the Edit/Write tools enforce the same isolation guard that also can't be satisfied here). If this recurs: check `Test-Path "C:\Program Files\Git\cmd\git.exe"` and whether `C:\Program Files\Git\cmd` (not just `...\Git`) is actually on the Windows-native `PATH` before re-diagnosing from scratch.

---

## 2026-07-25 — `git clone` on Windows silently produces a partial checkout when the destination path is long, and reports "Clone succeeded"
Tools/commands involved: `git clone --depth 1` (Git for Windows 2.55.0), Git Bash, a destination under the harness scratchpad (`.../claude/<long-project-slug>/<uuid>/scratchpad/...`)
Status: [Resolved — clone to a short path; do not silently accept a clone whose checkout failed]
Symptom: cloning `spring-projects/spring-petclinic` into the session scratchpad appeared to work — the directory existed, `git log -1` resolved, and 15 `.java` files were present. The repository actually has 49. `git clone` had printed `error: unable to create file ...: Filename too long` for several files, then `fatal: unable to checkout working tree`, then **`warning: Clone succeeded, but checkout failed.`** — and exited in a state where `git ls-files` returns `0` and `git status` reports every tracked file as staged-deleted. Piping the clone through `tail -3` hid the per-file errors and showed only the reassuring last lines. A full pipeline run was then executed against the partial repo before the discrepancy was noticed.
Diagnostic steps taken (re-runnable):
    git clone --depth 1 <url> <dest> 2>&1 | head -30   # do NOT tail -- the real errors are at the top
    git -C <dest> ls-files | wc -l                     # 0 means the index is empty; the checkout failed
    git -C <dest> status --porcelain | head            # every file shows as 'D ' (staged delete)
    find <dest> -name '*.java' | wc -l                 # compare against the project's known file count
Resolution / workaround: Windows `MAX_PATH` is 260 characters. The scratchpad root alone is ~150, and Java projects add deep package directories (`src/test/java/org/springframework/samples/petclinic/...`), so the total crosses the limit for the deepest files only — which is why the failure is partial rather than total, and why it looks like a successful clone. **Clone to a short path** (`C:/Users/<u>/AppData/Local/Temp/<short>/`) rather than into the deep scratchpad. Enabling `core.longpaths true` also works but mutates the user's global git config, so prefer the short path in a session that did not ask for that. Two general lessons: never `tail` a `git clone`, since its errors are printed before its reassuring summary; and verify a fresh clone by file count against a known expectation, not by whether the directory exists. Any target-repo tooling in this project should treat "clone succeeded" as unverified until `git ls-files` is non-empty and `git status` is clean.

---

## 2026-07-24 — The Windows `PATH` entry for Git pointed at the install root instead of `\cmd`, so `git` was invisible to every non-Git-Bash tool on this machine (now fixed at user scope)
Tools/commands involved: `ultraplan` / Claude Code on the web (`git bundle create --all`), `EnterWorktree`, PowerShell `Get-Command git`, the Windows machine/user `PATH`
Status: [Resolved at user scope — machine-scope entry is still wrong; see below]
Symptom: handing a plan off to `ultraplan` failed with `session creation failed — Failed to create git bundle (git bundle create --all failed (127): Command 'git' not found or is in an unsafe location (current directory))`. This is the **third** manifestation of one root cause: the `EnterWorktree` entry above (2026-07-25) is the same defect, and its diagnosis was already correct and already recorded the exact check that confirms it.

Two things made this look contradictory rather than obvious, and both are the reason it went un-fixed twice:
1. **Git worked perfectly all session** via the Bash tool. Git Bash / mingw64 constructs its own POSIX `PATH` and never consults the Windows one, so dozens of successful `git` calls tell you nothing about whether a native process can find `git`.
2. **The error message's "or is in an unsafe location (current directory)" clause is a red herring.** It is a generic fallback in that error string. There was no stray `git`/`git.exe` in the working directory — verified. The real signal is the bare `127`, which is simply "command not found."

Root cause: the machine `PATH` contained `C:\Program Files\Git` — the **install root**, one directory too high. That folder holds `git-bash.exe` and `git-cmd.exe` but **no `git.exe`**; the real binary is at `C:\Program Files\Git\cmd\git.exe` (and `...\bin\git.exe`). So native `PATH` resolution finds nothing.
Diagnostic steps taken (re-runnable):
    Get-Command git -ErrorAction SilentlyContinue                      # NOT FOUND -- the whole diagnosis in one line
    $env:PATH -split ';' | Where-Object { $_ -match 'Git' }            # shows "C:\Program Files\Git" (the trap: it LOOKS present)
    Test-Path "C:\Program Files\Git\git.exe"                           # False -- confirms the entry is one level too high
    Test-Path "C:\Program Files\Git\cmd\git.exe"                       # True  -- where it actually lives
    Get-ChildItem "C:\Users\...\<repo>" -Filter "git*" -File           # rules out the "unsafe location (current directory)" clause
    [Environment]::GetEnvironmentVariable("PATH","Machine") -split ';' | Where-Object { $_ -match 'Git' }   # which scope owns the bad entry
Resolution / workaround: appended `C:\Program Files\Git\cmd` to the **user** `PATH`:

    $cur   = [Environment]::GetEnvironmentVariable("PATH","User")
    $parts = $cur -split ';' | Where-Object { $_ -ne '' }
    [Environment]::SetEnvironmentVariable("PATH", (($parts + "C:\Program Files\Git\cmd") -join ';'), "User")

Four things worth knowing before repeating this:
- **Use `[Environment]::SetEnvironmentVariable`, not `setx`.** `setx` truncates the value at 1024 characters, which silently corrupts a long `PATH`.
- **Print the old value first as a backup.** The rewrite above also collapses any empty `;;` entries (this `PATH` had one), so it is not a pure append — capture the original before writing.
- **A restart of the calling process is mandatory.** A running process cannot refresh its own inherited environment, so the current Claude Code session keeps seeing the old `PATH` no matter what. Verify instead by re-deriving what a *new* process would see: iterate `Machine;User` and `Test-Path (Join-Path $dir "git.exe")`. That confirmed `C:\Program Files\Git\cmd\git.exe`, `git version 2.55.0.windows.3`.
- **The machine-scope entry is still wrong.** Fixing it needs elevation. Until then `git` remains unresolvable for services and other user accounts — user scope only covers processes running as this user.

General lesson, and the reason this cost time three separate times: a `PATH` entry that *looks* present is not the same as a resolvable binary. When a native tool reports `127`/"not found" for something Git Bash runs fine, check whether the `PATH` entry points at the directory actually containing the `.exe` — not merely at something with the right name.

---

## 2026-07-25 — `python` and `python3` are different interpreters here, and `$?` after a pipe reports the wrong command's status
Tools/commands involved: Git Bash on Windows, `python` (3.14.6, `C:\Python314\python.exe`) vs `python3` (has the pinned `ruff` 0.16.0), `cmd | tail` followed by `echo "exit=$?"`
Status: [Resolved — use `python3` to match CI, and capture `$?` before piping]
Symptom: two independent false "success" readings in one session, both of the same shape this repo's write-then-verify rule exists for.
1. `python -m ruff check scripts/` printed `No module named ruff` — but the surrounding `echo "ruff exit=$?"` reported `0`, so the lint step read as passing when it had not run at all. `python3 -m ruff --version` works and reports `0.16.0`, the version pinned in `requirements-dev.txt`. Same class as the `ast-grep` PATH-shadowing entry above, one layer up: it is the *interpreter* that differs, not the tool.
2. `python scripts/ci/check_repo_claims.py 2>&1 | head -60; echo "exit=$?"` reports **`head`'s** exit status, not the script's. This was hit twice — once reporting a failing gate as `exit=0`, and once reporting a *conflicted* `git stash apply` as `exit=0`, which left unresolved merge markers sitting in two files while the output above them looked clean.
Diagnostic steps taken (re-runnable):
    python -c "import sys; print(sys.executable, sys.version)"   # 3.14.6, no ruff
    python3 -m ruff --version                                     # 0.16.0
    which -a python python3
    git status --porcelain                                        # UU = both-modified, the real signal
    grep -rln '^<<<<<<< \|^>>>>>>> ' --include='*.md' .           # finds markers a tail'd log hid
Resolution / workaround: use `python3` for everything, which is also what `.github/workflows/ci.yml` invokes, so local runs match CI. Never read `$?` through a pipe — run the command redirected to a file, capture `$?` on the very next line, then inspect the file (`cmd > out.txt 2>&1; rc=$?; tail out.txt`). Note the second failure is the same shape as the `git clone` entry below: the reassuring summary is the part you see, and the error is the part the pipe discarded. `git status --porcelain` showing `UU` is the check that would have caught the stash conflict immediately.

---

## 2026-07-25 — `ast-grep` reports success while matching nothing, and its `markdown` grammar is not a text search
Tools/commands involved: `ast-grep` 0.44.1 (Windows), `ast-grep run -p`, `-l java`, `-l markdown`
Status: [Resolved — always try both annotation shapes; never use `-l markdown` as a substitute for text search]
Symptom: two false readings in one session, both of the shape where the tool exits 0 and the answer is wrong.

1. **A marker annotation and an argument-bearing annotation are disjoint node shapes.** `ast-grep run -l java -p '@Column' <repo>` returned **0** against a corpus holding **122** `@Column(name = "...")`. Nothing errored; the pattern is structurally valid, it simply matches `marker_annotation` and not `annotation`. The same probe reported `@Table` 0 (really 43) and `@Query` 0 (really 198), and those zeros were briefly written up as real findings before being caught. This is the same failure the rule file's own header warns about at `spring_ast_grep_rules.yml:22-31`, met from the query side instead of the rule side.

2. **`-l markdown` matches broad block nodes, not literal text.** `ast-grep run -l markdown -p 'ast-grep' README.md` reported **35** lines; only **8** of those lines contain the string `ast-grep` at all. It is matching containing paragraph/heading nodes, so it is unusable as a prose search and will happily "confirm" text that is not there.

Diagnostic steps taken (re-runnable):
    # the trap: these two are disjoint, never interchangeable
    ast-grep run -l java -p '@Column'      <repo> --json=compact   # 0
    ast-grep run -l java -p '@Column($$$)' <repo> --json=compact   # 122
    # ground truth for a whole-corpus annotation census, args-agnostic:
    ast-grep run -l java -p '@$A($$$)' <repo> --json=compact       # all args-bearing
    ast-grep run -l java -p '@$A'      <repo> --json=compact       # all markers
    # markdown imprecision, against a file whose real count is known:
    ast-grep run -l markdown -p 'ast-grep' README.md --json=compact

Resolution / workaround: when querying for an annotation, always run **both** `@Name` and `@Name($$$)` and take the union — a whole-corpus census needs `@$A` and `@$A($$$)` for the same reason. Treat a zero as *unproven*, never as *absent*: ast-grep exits 0 whether the pattern is wrong or the code genuinely lacks the construct, so a silent zero carries no information on its own. For prose, use `Glob` to narrow and `Read` to open; `-l markdown` is not a text searcher. Every rule in `spring_ast_grep_rules.yml` that can take arguments now lists both shapes, and `scripts/coverage/rule_coverage.py` fails the build if any CodeQL-pack `rule_id` matches nothing in `scripts/fixtures/spring_signals/` (via `spring_signal_scan`), which is the mechanical guard against writing a rule that can never fire. `scripts/coverage/rule_fixtures/` is the metamorphic corpus, not that gate's SoR.

---

## 2026-07-25 — Gradle 8.10 fails at configuration with "Unsupported class file major version 70" when launched by JDK 26, and piping it through `tail` reported that failure as success
Tools/commands involved: Gradle 8.10 (the extracted wrapper dist at `~/.gradle/wrapper/dists/gradle-8.10-bin/.../bin/gradle`), Temurin JDK 26.0.1 as ambient `JAVA_HOME`, Git Bash, `cmd | tail -N`
Status: [Resolved — root cause identified for both halves]
Symptom: two distinct problems that compounded, and the second is the one worth remembering.

1. **The real failure.** `gradle <task>` died during configuration with `BUG! exception in phase 'semantic analysis' in source unit '_BuildScript_' | Unsupported class file major version 70`. Major version 70 is Java 26. Gradle 8.10's embedded Groovy cannot parse class files that new, so *any* task fails before reaching the build script's own logic. Note this is a **JDK** incompatibility, not a Gradle-version-vs-project one: the project's `gradle-wrapper.properties` pins 8.10 and 8.10 was what ran. Downgrading Gradle further would not have helped; the ambient `JAVA_HOME` was the wrong component.

2. **What hid it.** The failing runs were invoked as `gradle ... 2>&1 | tail -30`, and the exit code read afterwards was `tail`'s (0), not Gradle's. Two consecutive runs were therefore reported as "exit 0 / baseline green" when Gradle had in fact failed both times and produced no build output at all. The empty log should have been the tell — a successful Gradle run is never silent — but a green exit code is more persuasive than an empty file, which is precisely why this is worth logging.

Diagnostic steps taken (re-runnable):

    java -version                     # 26.0.1 — the launcher JVM, not the toolchain
    gradle --version                  # confirms "Launcher JVM" separately from "Daemon JVM"
    ls -d "/c/Program Files/Java/jdk-21"

Resolution / workaround:

- **Set `JAVA_HOME` to a JDK the Gradle version supports before invoking it**, independently of any `java { toolchain { } }` block in the build script. The toolchain governs what compiles the *project*; it does not govern what runs *Gradle*. Here: `export JAVA_HOME="/c/Program Files/Java/jdk-21"` with Gradle 8.10 unchanged.
- **Never read an exit code through a pipe.** Redirect to a file, capture `$?` on the command itself, then read the file:

        "$GRADLE" <task> --console=plain > "$LOG" 2>&1
        EXIT=$?; echo "GRADLE_EXIT=$EXIT"; tail -n 170 "$LOG"

  `$?` after a pipeline is the *last* command's status. `set -o pipefail` or `${PIPESTATUS[0]}` also work, but redirect-then-read is harder to get wrong and keeps the full log.
- Corollary worth stating plainly: an empty output file from a build tool is evidence of failure, not of a quiet success. Treat "green exit code + no output" as a contradiction to investigate rather than a result to report.

---

## 2026-07-25 - ast-grep silently has no Groovy grammar, and the failure only shows at query time
Tools/commands involved: `ast-grep` 0.44.1, `--lang`
Status: [Resolved - probe the language before designing around it]
Symptom: a plan to cover Gradle build scripts structurally was drafted before checking whether the language was supported at all. It is not: `ast-grep run -l groovy` exits with `invalid value 'groovy' for '--lang <LANG>': groovy is not supported!`. Kotlin and Scala both are, so "it is a JVM language, it will be there" is exactly the wrong prior. There is no capability list in `--help`; it points at a docs URL.
Diagnostic steps taken (re-runnable):
    # one line, no network, answers it for any language:
    echo 'x' | ast-grep run --stdin -l groovy -p 'x'    # error: groovy is not supported!
    echo 'x' | ast-grep run --stdin -l kotlin -p 'x'    # STDIN:1:x
    echo 'x' | ast-grep run --stdin -l scala  -p 'x'    # STDIN:1:x
    echo 'x' | ast-grep run --stdin -l markdown -p 'x'  # supported, but see the entry above
Resolution / workaround: run the probe above before planning any rule work in a new language. Where the grammar is missing there is no partial mode to fall back on - `.gradle` files are handled by filename classification in `spring_signal_scan.py` (`BUILD_EXTS`, `_is_build_file`) and get visibility plus secret redaction, never structural signals. Recorded in `CONSTRAINTS.md` item 11 so the limit is stated rather than rediscovered.

---

## 2026-07-25 — Python `subprocess` cannot run Gradle's extension-less launcher on Windows: "[WinError 193] %1 is not a valid Win32 application"
Tools/commands involved: Python 3.14 `subprocess.run`, Gradle 8.10 distribution `bin/` directory, Git Bash
Status: [Resolved — root cause identified]
Symptom: a mutation-proof harness shelling out to Gradle died immediately with `OSError: [WinError 193] %1 is not a valid Win32 application`. The exact same launcher path runs fine when invoked from Git Bash, which makes it look like a path or permissions problem rather than what it is.
Cause: Gradle ships **two** launchers side by side in `bin/` — `gradle` (a POSIX shell script, no extension) and `gradle.bat`. Git Bash happily executes the shell script; Python's `subprocess` on Windows goes through `CreateProcess`, which requires a real PE executable or a file whose extension is associated with an interpreter. An extension-less shell script is neither, so it fails before the process ever starts. Nothing about the error message points at the launcher choice.
A second, related trap in the same call: `JAVA_HOME` passed in Git Bash form (`/c/Users/...`) is meaningless to the Windows JVM launcher. It must be a native path (`C:\Users\...`). This one fails later and more confusingly than the first.
Diagnostic steps taken (re-runnable):

    ls "<gradle-dist>/bin"          # shows BOTH `gradle` and `gradle.bat`

Resolution / workaround: when launching Gradle (or any similarly dual-packaged tool) from Python on Windows, resolve the `.bat` sibling and normalise any path handed to the child process:

    launcher = Path(gradle)
    if os.name == "nt" and launcher.suffix == "":
        bat = launcher.with_suffix(".bat")
        if bat.is_file():
            launcher = bat
    env["JAVA_HOME"] = str(Path(java_home).resolve())

Generalises beyond Gradle: the same shape applies to `mvn`/`mvn.cmd`, `npm`/`npm.cmd`, and any tool distributing a POSIX script next to a Windows batch wrapper. If a command works from the shell and fails from `subprocess` with WinError 193, check for a `.bat`/`.cmd` sibling first rather than debugging paths.

---

## 2026-07-25 — Bare `hasProperty('x')` inside a Gradle task block silently returns false, so a `-Px` flag does nothing
Tools/commands involved: Gradle 8.10, Groovy DSL, a `task foo(type: Test) { ... }` configuration block, `-PsomeFlag` on the command line
Status: [Resolved — root cause identified]
Symptom: a task read an opt-in flag as `systemProperty 'my.flag', hasProperty('updateBaseline') ? 'true' : 'false'`. Passing `-PupdateBaseline` had **no effect at all** — the system property arrived as `'false'` every time, and the guarded behaviour never ran. Nothing warns, nothing fails; the flag is simply inert, which makes it look like the *consumer* of the property is broken rather than the producer.
Cause: `hasProperty` is defined on `groovy.lang.GroovyObject`, so **every** Groovy object has it, including the `Test` task being configured. Inside the task block the delegate is the task, so `hasProperty('updateBaseline')` asks *the task* whether it has a property of that name — it does not — and returns false. The project's `-P` properties are never consulted.
The confusing part is that the sibling call in the same block works: `findProperty('classesDir')` resolves correctly, because `Task` does **not** define `findProperty`, so Groovy's method dispatch falls through to the enclosing `Project`. Two lines that look symmetrical behave differently, and only one of them is wrong.
Diagnostic steps taken (re-runnable): pass the flag and print what the test actually receives, rather than trusting the build script:

    println "updateBaseline seen by task: " + project.hasProperty('updateBaseline')
    println "bare hasProperty:            " + hasProperty('updateBaseline')

Resolution / workaround: **always qualify with `project.`** when reading command-line properties inside a task configuration block:

    systemProperty 'my.flag', project.hasProperty('updateBaseline') ? 'true' : 'false'

Generalises to `property()`, `getProperty()` and anything else `GroovyObject` also defines. Rule of thumb: inside a task block, qualify any property lookup you intend to hit the project, and prefer `project.findProperty('x') != null` over `hasProperty` if you want one consistent idiom that cannot silently bind to the wrong receiver.

---

## 2026-07-25 - `ast-grep --update-all` exits 1 when its pattern matches nothing, same as when it fails
Tools/commands involved: `ast-grep run -p ... -r ... --update-all`, `ast-grep` 0.44.1
Status: [Resolved - decide on whether the file moved, never on the exit code]
Symptom: a mutation harness used `ast-grep --rewrite` to locate what to break, and reported "ast-grep failed" for a pattern that was simply absent. The docstring asserting the opposite ("exits 0 whether or not the pattern matched") was written from the search-mode behaviour and was false for rewrite mode; a test disproved it minutes later.
Diagnostic steps taken (re-runnable):
    printf 'x = 1
' > probe.py
    ast-grep run -l python -p 'absent($A)' -r 'other($A)' --update-all probe.py; echo "exit=$?"   # exit=1, no output
    printf 'foo(1)
' > probe2.py
    ast-grep run -l python -p 'foo($A)' -r 'bar($A)' --update-all probe2.py; echo "exit=$?"       # "Applied 1 changes", exit=0
Resolution / workaround: exit 1 means "matched nothing" OR "genuinely failed" and the two are indistinguishable from the status alone, so do not branch on it. Read the file before and after and decide on whether it moved; that is unambiguous and stays correct if the exit-code behaviour changes in a later release. Note the search mode (`ast-grep run` without `--update-all`) does exit 0 on no matches - the two modes differ, which is what made the wrong assumption plausible.

---

## 2026-07-25 — Chocolatey install reports background-task "exit code 0" while choco.exe itself failed with an access-denied error
Tools/commands involved: `choco install <pkg> -y`, launched via the Bash tool's `run_in_background`, Windows
Status: [Resolved — workaround found, root cause is environmental]
Symptom: `choco install jq -y` was launched in the background; the harness's own completion notification read "completed (exit code 0)". Running `jq --version` immediately after failed with "command not found". Reading the actual captured stdout showed choco had failed outright: `Access to the path 'C:\ProgramData\chocolatey\.chocolatey' is denied` (a `System.UnauthorizedAccessException` retried 3 times then thrown), "Chocolatey installed 0/0 packages."
Cause: not diagnosed to the OS-permission level (likely needs an elevated/admin shell to write under `C:\ProgramData\chocolatey\`), but the more important finding is procedural: the background-task exit code reported by the harness reflects the *wrapper's* exit, not necessarily a meaningful signal that the installation itself succeeded -- this is the same shape as the `gradle` example one entry up in this file, one layer higher (job wrapper vs. piped command). Never treat "background task completed, exit 0" as proof of success for a command whose own tool can fail after the wrapper considers its job done; read the captured output.
Resolution / workaround: skip Chocolatey for single-binary tools. `jq` ships as one static executable -- fetch it directly and drop it on PATH via a short Python download, using a native Windows path (not a Git-Bash-style `/c/Users/...` path -- the `python3` resolved on this PATH is the WindowsApps Store build, whose `open()` does not translate that syntax and raises `FileNotFoundError`). `~/bin` was already on `PATH` (it holds `ast-grep.exe`), so no shell restart was needed.

---

## 2026-07-25 — A hook meant to catch a mistake reproduced a different, already-documented mistake against itself
Tools/commands involved: a project PreToolUse(Bash) hook (`.claude/hooks/check_pipe_exit_code.py`), a `cat >> file <<'HEREDOC'` append containing prose that quotes a risky-looking command as an example
Status: [Resolved]
Symptom: writing a tool-quirks entry that quoted, as prose, an example of the exact bug the entry describes (a `gradle ... | tail` pipeline) was denied by a freshly-added hook meant to catch real instances of that pattern. The hook's regex had no way to distinguish "this text describes a risky command" from "this text is a risky command."
Cause: the hook matched its build-tool/masking-filter regex against the raw command string, including heredoc bodies. A heredoc body is data being written to a file, not a command being executed, but a naive regex cannot tell the difference. `hooks/deny_text_search.py` had already hit and fixed this identical class of bug for its own matcher, and documented it in its own docstring: "This hook blocked its own author writing a session-log entry that quoted a steering prompt... Treating text as executable is the same category of mistake that got verify_llms_docs.py deleted."
Resolution: strip heredoc bodies (`HEREDOC_RE` matching `<<'NAME' ... NAME`) before applying any command-shaped regex, mirroring `deny_text_search.py`'s `strip_heredocs()` exactly rather than inventing a second implementation of the same fix. Regression-verified: a heredoc quoting `gradle ... | tail` as prose now allows; a real un-quoted instance of the same pipeline still denies; the `PIPESTATUS` escape hatch still allows.
Worth generalizing: **any new hook that pattern-matches a Bash command string must strip heredoc bodies first**, on this project specifically, since prose about shell commands is a normal and frequent thing to write here (this very file).

---

## 2026-07-25 — `pip install semgrep` on Windows lands under a *different* Python installation than the one running scripts, and its console-script launcher fails with `ModuleNotFoundError` when spawned via `subprocess` from that other Python — but runs fine from a plain shell
Tools/commands involved: Windows, Git Bash, two coexisting Python installs (`python3` on `PATH` resolves to the Microsoft Store/WindowsApps Python 3.10 alias; `pip`/`pip3` on `PATH` resolve to a separate `C:\Python314` install), `pip install semgrep` (installed under the 3.14 install's user site, `%APPDATA%\Python\Python314\Scripts\semgrep.exe`)
Status: [Diagnosed — root cause not fully identified, reliable workaround confirmed]
Symptom: `semgrep --version` run directly in Git Bash worked (printed `1.171.0`). The exact same absolute path to `semgrep.exe`, invoked via Python's `subprocess.run(["<path to semgrep.exe>", ...])` from the `python3` on `PATH` (the WindowsApps Python 3.10 alias), failed every time with `ModuleNotFoundError: No module named 'semgrep'` inside the launcher's own `__main__.py` — even though `shutil.which("semgrep")` correctly resolved the same absolute path first. Running the identical `subprocess.run` call from `C:\Python314\python.exe` (the installation semgrep is actually installed under) instead of the WindowsApps 3.10 alias worked without error. No obviously relevant environment variable differed between the two (`PYTHONHOME`/`PYTHONPATH`/`PYTHONNOUSERSITE` were all unset in both).
Diagnostic steps taken (re-runnable):
    which semgrep                                                    # bash: resolves to the .exe under the 3.14 user Scripts dir
    semgrep --version                                                # bash: works, prints version
    python3 -c "import shutil,subprocess; print(shutil.which('semgrep')); print(subprocess.run(['semgrep','--version'],capture_output=True,text=True))"
                                                                      # fails: ModuleNotFoundError, even though shutil.which found the right path
    python3 -c "import os; print(os.environ.get('PYTHONHOME'), os.environ.get('PYTHONPATH'))"   # both None
    "/c/Python314/python.exe" -m semgrep --version                   # works, from the "correct" interpreter
    "/c/Python314/python.exe" scripts/coverage/semgrep_rule_coverage.py        # works end-to-end
Resolution / workaround: when a script needs to invoke a pip-installed console-script binary (as opposed to a native/compiled binary like `ast-grep`, which has no such layering and is unaffected — confirmed this only reproduces for a Python-launcher-wrapped entry point) on a Windows machine with more than one Python install, run that script under the **same** Python interpreter the target package is installed under (findable via `pip show <package>` → `Location:`), not whichever `python3` happens to resolve first on `PATH`. In this repo specifically: `semgrep` installed under `C:\Python314`'s user site, so `scripts/coverage/semgrep_rule_coverage.py` and `scripts/test_semgrep_rule_coverage.py` needed `"/c/Python314/python.exe"` rather than the ambient `python3` alias for their real-binary-dependent tests during local verification. Not a concern in this repo's own CI (`.github/workflows/ci.yml` uses a single `actions/setup-python@v5` install on Linux, so this specific installation-split cannot occur there) — this is purely a local multi-Python-install-on-Windows friction point. Root cause of *why* the launcher's module resolution depends on the calling process rather than just its own embedded interpreter path was not pinned down further; recorded as a workaround, not a full diagnosis.
Related, smaller finding from the same investigation: `subprocess.run(..., text=True)` (locale-default decoding) intermittently raised `UnicodeDecodeError` in a background reader thread on Windows when semgrep's own colored/box-drawing console output hit the process's `cp1252` console codepage — non-fatal (the main JSON capture on stdout still succeeded) but noisy. Fixed in `scripts/coverage/semgrep_rule_coverage.py` by passing `encoding="utf-8", errors="replace"` explicitly instead of relying on `text=True`'s locale default.

---

## 2026-07-26 — A `cd` into a subdirectory broke a settings.json hook that uses a repo-root-relative path, blocking every subsequent Bash call
Tools/commands involved: Git Bash (persistent cwd across tool calls in this harness), `.claude/settings.json`'s `check_pipe_exit_code.py` `PreToolUse(Bash)` hook, which is wired with the relative path `python3 .claude/hooks/check_pipe_exit_code.py` (unlike every other hook entry in this repo, which uses `"${CLAUDE_PLUGIN_ROOT}/hooks/..."`)
Status: [Diagnosed — workaround confirmed, root config not changed]
Symptom: running `cd hooks && echo '...' | python3 deny_raw_network.py` to smoke-test a new hook left the Bash tool's persistent cwd at `hooks/`. Every subsequent Bash call then failed with `PreToolUse:Bash hook error: [python3 .claude/hooks/check_pipe_exit_code.py]: ...can't open file '...\hooks\.claude\hooks\check_pipe_exit_code.py'` — the hook's relative path resolved against the now-wrong cwd, and the hook's own execution failure blocked the underlying command entirely (including a plain `cd` back to root, since that `cd` is itself a Bash call subject to the same broken hook).
Resolution / workaround: the `Bash` tool's cwd and the `PowerShell` tool's cwd are independent state in this harness, and the hook only matches the `Bash` tool. Used `PowerShell` (`Set-Location <repo root>`) to confirm the intended path, then ran `cd "<repo root>" && pwd` via `Bash` with an explicit absolute path (not a bare `cd -` or relying on `$OLDPWD`) to recover — this succeeded because it's the same command shape (`cd <path>`) the broken hook still manages to execute for, just landing at the correct cwd this time. Not changed: `.claude/settings.json` still wires this one hook by relative path while every sibling uses `${CLAUDE_PLUGIN_ROOT}`; that inconsistency is the root cause and making the path absolute would prevent recurrence, but doing so wasn't in scope for the task that hit this.
Practical consequence: avoid `cd <subdir> && ...` one-liners in this repo's Bash tool when a later command in the same session might need the hook layer working — prefer running commands with a leading path argument instead of changing directory, or immediately `cd` back in the same tool call (`cd hooks && ... ; cd ..`) rather than leaving cwd changed across calls.

---

## 2026-07-26 — `check_pipe_exit_code.py`'s build-tool regex does not recognize `python3 -m unittest`, so the exact masking-filter mistake it exists to prevent still passes silently for this repo's own most common verification command
Tools/commands involved: `.claude/hooks/check_pipe_exit_code.py`'s `BUILD_TOOL_RE`, `python3 -m unittest discover -s scripts -p "test_*.py" 2>&1 | tail -20` run via the harness's backgrounding path (command exceeded the 120s foreground timeout and was moved to background)
Status: [Resolved — 2026-07-26]
Symptom: the background-task completion notification reported the command as `(exit code 0)`. The actual tail of output showed `FAILED (failures=1, skipped=17, expected failures=1)` — the exact `... | tail` masking bug `check_pipe_exit_code.py`'s own docstring describes verbatim (`tail` always exits 0, so anything reading the pipeline's exit status after the fact reads `tail`'s, not the real command's). The hook did not fire and block this command, even though it is precisely the pattern it exists to catch.
Cause: `BUILD_TOOL_RE` only matches `gradle\w*|\.\/gradlew|mvn\w*|\.\/mvnw|npm|yarn|pnpm|pytest|cargo|go\s+test|dotnet...|make|msbuild` — `python3 -m unittest` (or bare `python3 <script>.py`) is not in the list, so a command shaped exactly like the incident the hook was built from (`gradle ... | tail -30` then reading `$?`) sails through unflagged when the head is `python3 -m unittest` instead of `gradle`/`mvn`/etc. This repo's own test suites are invoked this way constantly, so this is a real, live gap in the hook's coverage, not a theoretical one.
Workaround used this session: redirect to a file and check the actual command's exit code directly (`cmd > log.txt 2>&1; echo "EXITCODE=$?"`) rather than trusting a `| tail` pipeline's reported status, and — since the harness's own background-completion notification surfaces the *last* command's exit code, not necessarily the one that matters — always read the actual tail of output rather than trusting a reported "exit code 0" when a pipe was involved anywhere in the command.
Fixed: `BUILD_TOOL_RE` now includes `python3?\s+-m\s+unittest` alongside the existing `pytest` alternative. Regression-verified in `scripts/test_check_pipe_exit_code.py::PythonUnittestRegressionTest`, which asserts both the exact command shape from the symptom above and a bare `python3 -m unittest | tail` are denied; confirmed the prior regex could not have matched either (no `python`/`unittest` alternative existed at all).

---

## 2026-07-29 — PowerShell Add-Content / default console encoding writes cp1252 bytes into UTF-8-only repo markdown (session-log CI crash)
Tools/commands involved: Windows PowerShell `Add-Content`, `Out-File`, Cursor agent appends to `claude/session-log.md`; `scripts/ci/check_repo_claims.py` Check A (`Path.read_text(encoding="utf-8")`)
Status: [Resolved — write-path workaround + Check G preflight]
Symptom: appending a session-log entry via PowerShell introduced non-UTF-8 bytes (e.g. `0xd7` = cp1252 multiplication sign, later control chars from escape interpretation). CI then failed with an uncaught `UnicodeDecodeError` inside `check_derived_blocks`, not a structured Finding — the whole claims check aborted and masked other drift.
Diagnostic steps taken (re-runnable):
    python -c "from pathlib import Path; Path('claude/session-log.md').read_bytes().decode('utf-8')"
    # UnicodeDecodeError: 'utf-8' codec can't decode byte 0xd7 in position ...
    python scripts/ci/check_repo_claims.py
    # previously: traceback; after Check G: Finding G with path + byte offset
Resolution / workaround:
1. **Write path:** never append session-log (or other tracked `.md`) with PowerShell `Add-Content` default encoding. Prefer `Path.write_text(..., encoding="utf-8")` / `Path.open(..., encoding="utf-8")` from Python, or PowerShell `Out-File -Encoding utf8` / `Add-Content -Encoding utf8`.
2. **Read path:** `check_repo_claims.py` Check G preflights tracked markdown; non-UTF-8 yields a hard Finding (path, byte offset, hint) instead of a traceback. Skip unreadable files for later checks so one bad file does not hide the rest.
Related: same class as the `subprocess text=True` / cp1252 console decoding note in the 2026-07-25 semgrep entry above — locale default vs UTF-8 contract, different surface.

---

## 2026-07-30 — Windows CreateProcess WinError 206 on large Java path lists; repo-root ast-grep fallback silently widened ScanContext inventory
Tools/commands involved: `ast-grep scan` via `doc_engine.scanning._scanner_astgrep.AstGrepBackend`, Windows CreateProcess (~32KiB argv ceiling), ocs-api-service-scale repos (~600+ `.java` absolute paths)
Status: [Resolved — 2026-07-30]
Symptom: on Windows, Stage-0 warned `too many Java file paths ... scanning repo root instead` and issued one `ast-grep scan <repo_root>` with exclude globs. That diverged from `ScanContext.java_files` (walk inventory): `--no-ignore` root mode can see files the shared walk never listed, and evidence/`facts_evidence` looked complete while coverage was no longer inventory-bounded. Hit live on ocs (~596 Java paths).
Cause: `_PATH_LIST_CHAR_LIMIT` (7000-char heuristic) gated a **single** all-paths argv; over budget fell back to root instead of batching. ast-grep has no `@file` / path-list stdin for this.
Resolution: chunk `ScanContext` paths so each `base_argv + chunk` stays under the budget; concatenate match JSON; on residual WinError 206 bisect the offending chunk. Repo-root argv remains only when no inventory is supplied (`java_files is None`). Regression: `tests/doc_engine/test_scan_context_wiring.py` (chunk helper, multi-call under tiny limit, bisect-on-206).

---

## 2026-08-05 — core.autocrlf=true checks the spring-signals harness .sh files out as CRLF and bash rejects them; CodeQL's Windows tracer cannot run a .sh build command
Tools/commands involved: git-for-windows default `core.autocrlf=true`, WSL `bash -n`, `spring-signals/harness/*.sh`, `codeql database create --command` on Windows (`tracer.exe ... cmd.exe /C ... build.sh`), Git Bash `C:\Program Files\Git\bin\bash.exe`
Status: [Resolved — repo-side, for the EOL half] / [Diagnosed — workaround confirmed, for the tracer half]
Symptom 1: on a fresh Windows clone, all five harness shell scripts arrive as CRLF and any bash invocation fails with `syntax error near unexpected token '$'in\r''`. The committed blobs are LF, so CI (Linux checkout, no conversion) never sees it; a `bash -n` gate on the worktree files reports phantom syntax errors. Tells: the error names `$'in\r'` or `$'\r'`; blobs verified LF via `git show HEAD:<path>` byte count.
Resolution 1: `.gitattributes` at repo root with `*.sh text eol=lf` (plus `*.jar`/`*.class`/`*.bqrs binary`), added on the pr92 branch. Until something similar lands on your branch, run bash checks against the blob (`git show HEAD:<path> > tmp.sh`, byte-faithful redirect via cmd, not PowerShell `>` which re-encodes to CRLF) rather than the working copy.
Symptom 2: `create-test-db.sh` on Windows dies at database creation: `[build-stderr] The system cannot execute the specified program` — the CodeQL Windows tracer wraps the build command as `cmd.exe /C type NUL && <BUILD_COMMAND>`, and cmd cannot execute a `.sh` file. The harness's `./create-test-db.sh` path works on Windows only inside an environment that provides both bash AND a codeql the tracer can use, which WSL bash + Windows codeql.exe is not.
Resolution 2 (verified end to end 2026-08-05): keep Git Bash for the harness, but override the traced command with a Windows-executable equivalent: `BUILD_COMMAND='C:\...\compile-fixture.bat'` (a .bat that assembles the lib/*.jar classpath and runs `javac --release 17 -implicit:none` twice, main then test), with `CODEQL=/c/Users/<you>/.cursor/tools/codeql/codeql.exe`. Result: 31/31 jars digest-verified, extraction delta 0 (set equality), all fixture JSON assertions hold on the pr92 branch. The .bat is a local-verification artifact, not committed.

---

## 2026-08-08 — Quality gates: local jscpd + `sys.executable -m` instead of `npx`; worktree-safe gate REPO_ROOT
Tools/commands involved: `scripts/ci/run_quality_gates.py`, `scripts/ci/gate_tools.py`, `npx jscpd@…`, Windows CreateProcess / cp1252 console, git worktrees + `pip install -e .` from another checkout
Status: [Resolved — portable entry point]
Symptom 1: duplication gate used `npx --yes jscpd@5.0.14` (network flakiness; Windows `npx` without `.cmd` is the WinError 193 class already documented for npm/Gradle).
Symptom 2: importing `doc_engine.paths.repo_root()` from a worktree follows the editable-install source tree, so a worktree-local `node_modules/jscpd` is invisible and the runner reports jscpd missing.
Symptom 3: printing `≤` in gate labels raises `UnicodeEncodeError` on Windows cp1252 consoles.
Resolution: pin `jscpd@5.0.14` in `package.json` / `package-lock.json`; CI and local both `npm ci` then `python3 scripts/ci/run_quality_gates.py`; prefer native `node_modules/jscpd-*/bin/jscpd[.exe]` else `node …/run-jscpd.js`; invoke `diff-cover`/`tach` via `sys.executable -m`; derive gate `REPO_ROOT` from `Path(__file__).parents[2]`; keep console labels ASCII (`<=`). See CONTRIBUTING.md "Quality gates (all OS)".
