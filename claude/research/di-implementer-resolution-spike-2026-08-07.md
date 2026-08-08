# Spike: DI / implementer resolution (E5-S1)

Date: 2026-08-07  
Status: spike only — **do not start E5-T\* until E1–E3 are stable in CI**

## Problem

`dependents` / `cross_group_edges` resolve **import/package text** only.
`@Autowired` / constructor injection on an **interface** does not appear as an
import of the implementer — documented in `CONSTRAINTS.md` Known precision and
`build_cross_group_edges.py` header.

## Options

| Approach | Pros | Cons |
|----------|------|------|
| **A. CodeQL** type hierarchy + Spring injection | Precise; fits existing scanner | Needs DB + often `--allow-codeql-build`; trust model |
| **B. ast-grep** `@Service`/`@Component` + name match to interface | Hermetic, fast | Fragile on naming; misses config/@Bean |
| **C. Classpath / bytecode** | Sees real bindings | Heavy; not Stage-0 default |

## Recommendation

1. Prefer **A** as an optional CodeQL rule emitting `injection__implements` (or
   facts predicate) when `codeql` scanner enabled — same merge path as other
   evidence buckets.
2. Keep import arcs as `exact` / `package-fanout`; add a **separate** confidence
   channel `injection` on dependents so we never lie about import edges.
3. Hermetic fixture: interface + two `@Service` implementers + `@Autowired`
   consumer under `scripts/fixtures/spring_signals/` (or dedicated DI fixture).
4. Gate behind E1–E3 green; do not block context_packet on DI completeness.

## Exit for starting E5-T1

- [ ] E1 context_packet + mutator green in CI
- [ ] E2 freshness labels green
- [ ] E3 MCP adapter hermetic tool-call test green
- [ ] This memo reviewed; CodeQL pack owner named
