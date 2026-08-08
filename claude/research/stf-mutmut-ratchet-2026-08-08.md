# Nightly mutation ratchet (STF)

Target package: `src/stf/`

## Named mutants (CI)

```bash
python -m stf seed-tasks --target-dir specs/pr-94-query-surface
python -m stf mutate --target-dir specs/pr-94-query-surface --mode bad-dep
# expect exit 0 from mutate (= lint failed on mutant)
```

Modes: `bad-dep|no-phase|bad-inventory|no-acceptance|bad-blocker|cycle`

## mutmut (nightly, optional)

```bash
pip install mutmut
mutmut run --paths-to-mutate src/stf/graph --paths-to-mutate src/stf/validators
```

Record surviving mutants; ratchet must not increase survivors without ADR.
