# Adjudication: adversarial review of Wave 1 PR / plan

**Subject:** External review of Wave 1 (`wave1-gates-untrusted-tree-hygiene` @ `d708992` and the Wave 1 plan)  
**Role:** Principal engineer — verify the review against Tier A on this branch; do not defend Wave 1 by default.  
**Date:** 2026-08-06

---

## 1. Bottom line

The review is **directionally excellent** and better calibrated to the locked threat model (*untrusted target repos*) than Wave 1’s own framing of H1. Its central thesis is **CONFIRMED**:

> Under UNTRUSTED, allowlisting build-tool *names* is not a control against CodeQL `--command` execution inside `--source-root`.

Wave 1 still ships real foot-gun removal (mvnEvil, shells, YAML stripping, timeouts, symlink skip on the ScanContext walk, personal CodeQL path). Those remain worth keeping. What the review correctly names as **missing** is: treating CodeQL *build mode itself* as a trust-gated capability, and the `/tmp` results-cache forgery path.

Two of the reviewer’s “fix Wave 1” claims need correction against **this branch** (see §3): H7’s five CodeQL calls already share `_run_codeql(timeout=…)`, and `is_path_inside_root` already uses `Path.relative_to` (not a string prefix).

---

## 2. Central thesis — UPHELD (High → Critical under untrusted+host-you-care-about)

**Witnesses (this branch):**

```281:286:src/doc_engine/scanning/support/_codeql_runner.py
    cmd = [
        str(codeql_path), "database", "create", str(db_path),
        "--language=java",
        f"--command={build_command}",
        f"--source-root={repo_path}",
    ]
```

Live allowlist probe (same interpreter as CI):

| Input | Result |
|-------|--------|
| `gradlew -I /tmp/evil.gradle build` | **accepted** |
| `mvn -s evil-settings.xml compile` | **accepted** |
| `cmd /c gradlew.bat clean` | rejected (second token basename `c`) |
| `bash.exe gradlew clean` | accepted |

So:

1. **Attacker-controlled `gradlew`/`mvnw`** — basename allowlist means “run bytes from the tree.” CONFIRMED as category error for UNTRUSTED.
2. **`gradle`/`mvn` from PATH** — still execute attacker `build.gradle` / `pom.xml`. CONFIRMED.
3. **Arg injection without metacharacters** — CONFIRMED (`-I`, `-s`).

**Nuance vs prior adjudication:** that doc already said allowlist is necessary-but-not-sufficient and wanted operator-supplied build_command + sandbox. Wave 1 implemented allowlist + YAML stripping but **still permits** `doc-engine scan --scanners filesystem,codeql --build-command 'gradlew …'` against an untrusted tree. The review is right that this is the same RCE with CLI provenance.

**Recommendation (agree):** keep exact-basename hygiene; **reframe H1**; under `RepoConfigTrust.UNTRUSTED`, **refuse CodeQL build mode** unless an explicit operator escape (stronger than `--trust-repo-config` alone — e.g. `--allow-codeql-build` on a trusted host, or containerized runner). Sandbox-or-refuse is the control that matches the threat model.

---

## 3. Cache poisoning — UPHELD (severity host-dependent)

```115:116:src/doc_engine/scanning/support/_codeql_runner.py
def _cache_dir() -> Path:
    return Path(tempfile.gettempdir()) / "spring_signal_scan_codeql_cache"
```

```452:459:src/doc_engine/scanning/support/_codeql_runner.py
    if using_cache and scanner_version:
        cached_rows = _load_results_cache(...)
        if cached_rows is not None:
            return cached_rows
```

- Predictable shared temp dir + `mkdir(..., exist_ok=True)` + `json.loads` returned as evidence **before** queries / covering — CONFIRMED.
- Cache key omits CodeQL CLI version — CONFIRMED (`_cache_key` hashes repo+build_command+pack only; results key adds `scanner_version` but not CLI version).
- CWE-377/379 framing is fair on multi-user `/tmp` or shared runners.

**Severity:** Critical on shared CI / multi-user hosts; Low–Medium on a solo laptop with exclusive temp. The review’s question 2 is the right severity dial — answer it before ranking vs H1.

**Agree on fix direction:** user-owned `0700` cache (XDG/platformdirs), reject symlink takeover, re-validate rows or disable results cache on certified / CodeQL paths.

`REPO_ROOT = Path(__file__).resolve().parents[4]` — CONFIRMED brittle for wheel installs (DEFAULT_PACK_DIR). Separate Medium packaging defect; not the same as cache forgery.

---

## 4. Item-by-item on the Wave 1 plan / PR

| Item | Reviewer | Adjudication | Notes |
|------|----------|--------------|-------|
| **C1** | sound, under-specified | **UPHOLD + accept additions** | Catch is live. `json.JSONDecodeError` is **not** dead for non-JSONL: `validate_artifact_file` → `load_json` → raw `json.load` (only JSONL wraps). Cert-row FAIL witness in the test is a good addition; StageResult alone doesn’t prove cert fold. |
| **H1** | category error + cmd regression | **UPHOLD both** | Reproduced. Drop `cmd`/`powershell` from wrappers (or parse `/c`/`-File` properly). Reframe as foot-gun removal. Arg allowlist (`-I`) still open even after basename fix. |
| **N1** | Strategy vs Enum; gaps | **PARTIAL** | Sanitizer works; Enum+function is thin Strategy, not boolean soup across five modules with divergent logic. **Agree:** filter/clear `extra` under UNTRUSTED (today copied through — `repo_trust.py:52`). **Agree:** ignore YAML `compliance_profile` outright (we floor to CERTIFIED — equivalent outcome, simpler story). **Agree:** `find_repo_config` `.is_file()` follows symlinks — needs containment. `doc_taxonomy` path-traversal remains Tier C until call sites read. |
| **N3** | too narrow; TOCTOU | **UPHOLD scope gap; soften mechanism nits** | `partition_repo.dfs_file_list` uses `os.path.isdir` / recursive walk — dir symlink follow + loop DoS CONFIRMED. `_repo_content_hash` fallback has its own `os.walk` + exclude set CONFIRMED. **Correction:** Wave 1 `is_path_inside_root` already uses `relative_to`, not string prefix — `/repo` vs `/repo-evil` is handled. Symlink-gated resolve / `O_NOFOLLOW` still valid hardenings. |
| **H5** | correct | **UPHOLD** (already fixed on branch) | Env-first + no personal path. |
| **H7** | timeouts insufficient; five uncovered calls | **PARTIAL** | Process-group kill on timeout — **UPHOLD** (Gradle/CodeQL orphans). **REFUTE “five uncovered” on this branch:** all go through `_run_codeql(..., timeout=)`. Reviewer may have been reading the plan text / pre-PR tip. |
| **H2** | log OK; dual logging models | **UPHOLD** | Prefer one channel (`logging` or stderr) in `_merge_signals`. |
| **merge bugs while file open** | order bug + dead helper | **UPHOLD** | `merged_map = _build_entity_table_map_from_evidence(result)` runs **before** `result["evidence"] = …` → always `{}` when no backend map. `_merge_entity_table_map` defined, never called — only the inline copy is live. Zero-blast fixes; should have been in Wave 1 while the file was open. |
| **test_rejects_unknown_tool** | metachar false confidence | **UPHOLD** | Still `"curl … \| sh"` — rejected by `|`, not allowlist. Pipe-free curl case still missing. New mvnEvil tests are the real allowlist coverage. |
| **Pull C2 / H3 into Wave 1** | sequencing | **PLAUSIBLE** | Cheap, same functions. Not a defect in shipping Wave 1 without them; good follow-up. C2 is not a “coverage regression” of a shipped Wave 1 that never claimed C2 — it’s deferred debt. |

---

## 5. Answers to the reviewer’s two questions

**Q1 — CodeQL against repos you don’t control, on a host you care about?**  
Product default remains **yes, untrusted targets** (document *other people’s* Spring services). Therefore: sandbox-or-refuse CodeQL build under UNTRUSTED is Wave 1.5 / next PR, not a footnote. If an org only ever CodeQL-scans first-party trees, demote N1/H1 to hygiene and center on C1 + H7 + cache.

**Q2 — Shared CI / multi-user hosts?**  
Unknown for every deploy; **design for shared temp as the fail-closed default** (0700 user cache). Solo-dev exclusive temp makes cache Low — still fix, because the certified artifact chain must not silently trust world-writable JSON.

---

## 6. Revised next-PR backlog (post this review)

Ordered by bite ÷ blast under untrusted+shared-host defaults:

1. **Refuse or sandbox CodeQL build under UNTRUSTED** (real H1). Keep basename allowlist as hygiene; drop cmd/powershell wrappers; reject known-dangerous flags (`-I`, `--init-script`, `-s` without allowlist) if build mode remains reachable.  
2. **Cache hardening** — user-owned 0700 dir, no symlink hijack, validate or disable results cache. Include CodeQL CLI version in cache key.  
3. **`_merge_signals` order fix** + delete or wire `_merge_entity_table_map`; unify logging.  
4. **N3 extend** to `partition_repo` + `_repo_content_hash` (shared containment helper).  
5. **C2** registry-driven `_validate_outputs`; **H3** honor `end-stage`.  
6. **N1 polish** — clear `extra`; contain `.doc-engine.yml` path; optional Protocol policy if a second policy appears (YAGNI until then).  
7. Fix `test_rejects_unknown_tool` to pipe-free curl; add `gradlew -I …` rejection test once flag policy exists.  
8. C1 test asserts cert/stage bookkeeping records FAIL when wired through local_runner (or document StageResult as the unit under test).

---

## 7. Score for this PR review

| Dimension | Grade |
|-----------|-------|
| Factual accuracy vs this branch | High (with two stale/overclaimed notes: H7 uncovered calls; string-prefix containment) |
| Threat-model consistency | Excellent — better than Wave 1’s H1 framing |
| Severity judgment | Sound if Q1/Q2 answered “untrusted + shared” |
| Actionability | High — revised Wave 1 / Wave 1.5 is implementable |

**Disposition:** Treat this review as **accepted on the CodeQL+cache strategic gap**. Do not reopen “was Wave 1 wrong to ship foot-gun removal” — it wasn’t. Do not treat the allowlist as the untrusted-tree control — it isn’t.
