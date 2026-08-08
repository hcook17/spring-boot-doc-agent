# STF / query TDD map

Spoken-language helpers + fail-closed probes. Suites under `tests/stf/` and `tests/doc_engine/query_tdd/`.

| Layer | Location | Covers (user taxonomy mapping) |
|---|---|---|
| Unit (white-box) | `tests/stf/unit/` | Unit, development, shift-left |
| Property | `tests/stf/property/` | Property, conformance of budget/DAG algebra |
| Metamorphic | `tests/stf/metamorphic/` | Metamorphic, regression mutants |
| Contract | `tests/stf/contract/` | Contract, schema, output comparison (golden findings) |
| Integration | `tests/stf/integration/` | Integration, system (CLI pipeline), acceptance of plan-gate/SoD |
| Chaos / destructive | `tests/stf/chaos/` | Destructive, concurrent, smoke of atomic writes |
| Security / pen-style | `tests/stf/security/`, `query_tdd/` | Security, black-box confused-deputy, grey-box with env |
| Query hardening | `tests/doc_engine/query_tdd/` | Smoke/sanity, functional containment/budget, static schema checks |
| Eval | `tests/stf/unit/test_eval_scoring.py` | AI-assisted scoring stub, continuous KPI definition |

**Out of scope for this CLI (documented, not faked):** visual UI testing, full a11y browser matrix, alpha/beta user studies, i18n UI packs. Compatibility = Python 3.10+ via CI. Installation = `pip install -e .` + `python -m stf --help` smoke.

**Preset vs adaptive:** named mutants are preset; property loops over budgets/graphs are adaptive generators without Hypothesis pin (optional later).

**VCR:** not applicable (no HTTP SoR); transcript metrics stub stands in for session replay.
