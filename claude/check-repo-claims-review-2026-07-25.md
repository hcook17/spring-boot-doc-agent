# Review: `scripts/ci/check_repo_claims.py` — readability findings

Point-in-time review, 2026-07-25. **The file was untracked working-tree work at the time**, so
nothing here was applied to it — editing another session's in-flight file is how one side's work gets
lost. These are findings for its author to apply or reject.

Historical record by nature: if the file has moved on, prefer the file.

## The verdict first

This is well-crafted code. The difficulty is **density and ordering**, not sloppiness — a high ratio
of justification to mechanism, with the justification first. The reasoning is worth keeping; it is
in the wrong order. Everything below is about layering, not rewriting, and **nothing proposes
deleting an argument**.

## 1. Confirmed defect — the same eight strings, written twice

`:123-126` and `:137-140` both hold the identical tuple:

```python
"scripts/", "agents/", "skills/", "claude/", ".github/",
"baseline-reference/", ".claude/", ".claude-plugin/",
```

A reader has to eye-verify they match, and nothing keeps them matching. Worth fixing not only on
merit: this is the one file in the repo whose stated purpose is making "don't write the same fact
twice" enforceable.

```python
OWN_PATH_PREFIXES = (
    "scripts/", "agents/", "skills/", "claude/", ".github/",
    "baseline-reference/", ".claude/", ".claude-plugin/",
)
_OWN_PREFIX_ALT = "|".join(re.escape(p) for p in OWN_PATH_PREFIXES)
```

Now they are the same by construction.

## 2. Two axes, four constants, no map

`OWN_PATH_PREFIXES` / `OWN_ROOT_FILES` and `CURRENT_STATE_ROOT_DOCS` / `CURRENT_STATE_PREFIXES` are
two *independent* axes, and `CURRENT_STATE_ROOT_DOCS` is a subset of `OWN_ROOT_FILES`, which makes
the relationship look like an inconsistency until you work it out. One block comment drawing the map
once would let a reader slot every later constant into place:

```
# Two independent axes decide whether a path is inspected:
#   OWNERSHIP — is it in THIS repo?        (OWN_PATH_PREFIXES / OWN_ROOT_FILES)
#   RECENCY   — does it claim something about NOW, or record history?
#                                          (CURRENT_STATE_*)
# Check B needs both: a real repo path, in a present-tense doc.
```

## 3. Docstring order

82 lines, with the usage block at line 79. A reader who just wants to run it reads the argument
first. The repo now has a stated contract for this (`CONTRIBUTING.md`, "Module docstrings: reference
first, rationale second") and a check that enforces it against a baseline
(`scripts/ci/check_code_quality.py`) — this file is currently recorded as a pre-existing violation
rather than blocking, so it can be fixed whenever suits.

**Recommended against:** moving the essay to a separate `docs/` file. This repo's dominant failure
mode is prose drifting from code — prompt `07` carried a stale `status:` for weeks, `CONSTRAINTS.md`
cited `verify_llms_docs.py` after deletion, `12` named files that did not exist. A standalone
rationale doc is the highest-drift-risk location available, and this module exists to catch exactly
that. Keep it in the file; invert the order.

**Refinement worth applying while reordering:** split the prose by what kind of claim it makes.
Mechanism-explaining comments ("the ticked branch is first, so a path inside backticks is consumed
there and never double-counted") must stay adjacent to the code — drift there is a correctness bug.
Incident history (the `verify_llms_docs.py` deletion, the renumbering that broke `12`) already has a
home in `claude/session-log.md` and `CONSTRAINTS.md`; referencing it beats restating it, and
restating it is itself the duplication this file opposes.

## 4. Comments: lead with what, then justify

Many comments open with the road not taken ("Requiring a backtick there would mean checking
everything except the case that actually broke"). Excellent reasoning, unskimmable. One summary line
first lets a reader move on and loses nothing:

```python
# `bare` matches unbackticked paths that start with a repo directory.
# Needed because file *lists* are rarely backticked, and those were exactly
# the paths that broke.
```

## 5. A check registry

The docstring promises checks A–E; the code scatters them. A registry makes the correspondence one
glance instead of a search — and there is already in-file precedent for the pattern in the
`DERIVATIONS` dict, so this is consistency rather than a new idea.

## Not a finding — worth saying explicitly

The security reasoning behind the derived-block regex, and the analysis that got
`verify_llms_docs.py` deleted, are the sharpest things in the file. The ratchet-against-a-baseline
pattern is mature and is now used by `check_code_quality.py` too. None of the above touches any of
that.
