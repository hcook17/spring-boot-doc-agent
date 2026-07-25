---
name: directional-tests
description: Write tests that defend a named property and are proven able to fail, rather than tests that chase coverage. Use whenever adding or reviewing a test, a gate, a checker, or any assertion in this repo — before writing the test, to pick what it should defend, and after writing it, to prove it can go red. Covers the non-vacuity proof, invariants versus probes, keeping an assertion no wider than its name, asserting exit codes rather than internal issue lists, stating every bound, and wiring a new suite into CI so it actually runs. Distinct from claude/tool-quirks.md (ambient tool oddities) and claude/llms/ (PR verification commands) — this is about whether a test points at anything.
---

# Directional tests

## Why this exists

This repo does not have a coverage problem. It has ~800 functions across 16 suites, and adding
assertions is cheap. What is expensive — and what has actually gone wrong here, repeatedly — is
writing a test that *executes* code without *defending* anything.

A coverage-shaped test asks "did this line run?" A directional test asks "what would this catch, and
have I watched it catch it?" The second question is the whole skill.

Every rule below is a real incident in this repository, not a principle borrowed from a book.

## The rules

### 1. Name the property. The test name is the claim.

`test_scan` names a function. `test_entity_without_its_own_table_does_not_borrow_a_siblings` names a
property, and a reader can tell from the name alone what breaking it would mean. This repo is already
good at this — keep it that way, and treat a test name that names a *method* as a smell.

### 2. Prove the gate can fail. Do not assert that it should.

The standing rule here is that **a gate that cannot be shown to fail is not a gate**. Satisfy it by
injection, not by intent: break the thing, watch the test go red, restore it, and record that you
did. Before `test_enterprise_kitchen_sink.py` existed, every gate in this pipeline was proven only to
populate an issues list — never to actually fail a run.

### 3. Assert the observable outcome, not the internal artifact.

A checker that appends to a `findings` list and a checker that exits non-zero look identical from a
unit test that inspects the list. Assert the **exit code**. `check_pipeline_output.py` and
`check_code_quality.py` both split `exit_code()` into its own function precisely so the blocking
decision is testable rather than implied.

### 4. Prefer an invariant to a probe.

Measured in this repo, not assumed: a re-run-and-diff determinism probe **passed** against an unfixed
scanner, while the invariant `keys == sorted(keys)` caught the same bug. A probe compares two runs and
can agree on the same wrong answer. An invariant states what must be true of any run. Reach for the
invariant, and where the source is deliberately unsorted, assert the *inverse* rather than skipping.

### 5. A test must be non-vacuous everywhere it runs.

A "no backslash in the output" assertion is only meaningful on Windows — `os.path.relpath` never emits
one on POSIX, so in CI it would have passed forever while proving nothing. That is a green check
defending nothing. The fix was structural: extract the normalization into a pure function so the
property could be asserted on every platform (`partition_repo.to_posix`).

Ask of every new test: **on which platform, interpreter, or config is this assertion trivially true?**
If the answer is "the one CI uses," it is not a test.

### 6. Keep the assertion no wider than the name.

`test_every_steering_prompt_with_a_status_has_predicates` asserted over *all* missing findings. That
was the same thing while steering prompts were the only corpus — until `CONSTRAINTS.md` joined, and
the assertion silently became broader than the name promised. Scoping it back to its name was correct;
so was adding a companion non-vacuity test, because narrowing an assertion can hide the very
regression the wider version happened to catch. **When you narrow a test, add the guard that replaces
what you removed.**

### 7. State every bound. A silent limit reports a better number than the truth.

An extractor capped a status tag at 60 characters and silently dropped three claims — the long
`[New info — ...]` corrections, i.e. exactly the entries recording a previous claim going wrong.
Undercounting inflates a ratio. Worse, the ad-hoc count used to *verify* the undercount was itself
bounded and also wrong.

So: **verify your verification.** If a check applies a bound — top-N, a length cap, a sample, a hop
limit — the bound belongs in the output. Done and truncated are different words.

### 8. Beware the false PASS from your own harness.

A non-vacuity proof once reported success without running: `grep -c` printing `0` **exits 1**, which
short-circuited an `&&` chain, so the retry never executed and the exit code read belonged to `grep`.
Run proofs from a script file, capture `$?` on the very next line, and never read it through a pipe or
a chain. See `claude/tool-quirks.md`.

### 9. An unrun test is not a test.

`.github/workflows/ci.yml` enumerates suites by hand, so a new `test_*.py` does not run until it is
added. `check_repo_claims.py`'s check D fails the build for a suite that exists but is unwired — let
it. And run what you wrote *before* committing it; writing a suite and never executing it has happened
in this repo and produced eleven tests of unknown value.

## The procedure

**Before writing:** say out loud what failure this test would catch. If you cannot name a concrete
input and the wrong output it produces, you are about to write a coverage test. `10-review-persona-and-standards.md`
calls this a witness: a claimed defect is not a defect until you can state one.

**After writing:** break the code the test defends. Watch it go red. Restore. If it stayed green, the
test points at nothing — fix the test, not the code.

**When reviewing:** for each assertion ask (a) what property, (b) what breaks it, (c) where is it
trivially true. Three questions, and most weak tests fail the third.

## Mutation testing is this discipline, mechanised

Rule 2 is performed by hand today: break it, watch it go red, restore, write it down. That is
mutation testing done manually, once, with no artifact proving it happened. `mutmut` automates
exactly it. Treat a proposed test-quality control as an approximation of that ritual, and prefer the
one that runs on every commit over the one that runs when someone remembers.

## What this is not

Not a coverage target. This repo has no coverage threshold and should not acquire one: coverage
measures which lines ran, and every incident above happened in a line that ran. Not a style guide for
test naming either — that convention is already strong here. This is about whether a passing test
means anything.
