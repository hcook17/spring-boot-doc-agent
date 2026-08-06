# Symbol grammar

The eleven-column join is on `(file, symbol, rule_id)`. If three emitters
(CodeQL, ast-grep, semgrep) invent three symbol strings, the join silently
degrades to `(file, rule_id)` and the comparison it exists to support becomes
worthless. So `symbol` is defined once, in
`java-signals-lib/signals/Schema.qll::symbolOf`, and every query routes through
`_Common.qll::sym`. No query may hand-roll a symbol string.

## Columns: `symbol` vs `signal`

An earlier draft overloaded `symbol` to mean both "where this is" and "what was
detected", which is why `Persistence.ql` emitted a class name in one branch and
`javax.persistence.Column` in another. Those are separate concerns and are now
separate columns:

| Column | Meaning | Bound to |
|---|---|---|
| `symbol` | Code-location identity. The join key. | `symbolOf(e)`, always |
| `signal` | What was detected: annotation FQN, type FQN, property key, named-query name | per rule |
| `detail` | Free payload: query text, path, table, propagation, target FQN | per rule |

## Grammar

SCIP-inspired, deliberately simplified:

```
type       com.elsevier.eols.ocsapi.repository/TopicRepository#
nested     com.elsevier.eols.ocsapi.domain/Outer$Inner#
method     com.elsevier.eols.ocsapi.repository/TopicRepository#findByVtwId().
ctor       com.elsevier.eols.ocsapi.repository/TopicRepository#<init>().
field      com.elsevier.eols.ocsapi/CachingConfig#redisTemplate.
parameter  com.elsevier.eols.ocsapi/TopicController#get().(vtwId)
```

Annotations, statements and expressions resolve to the symbol of their nearest
named enclosing declaration.

## Known divergence from the L3 SCIP-inspired claim symbols

This is a **deliberate simplification**, not an alignment. Two differences:

1. **Overloads collapse.** Arity and parameter descriptors are omitted, so
   `findBy(String)` and `findBy(String, Pageable)` share a symbol. Cost: a
   handful of ambiguous rows in `NativeSql`/`ApiSurface` on overloaded
   repository methods. Benefit: an ast-grep or semgrep emitter can produce this
   grammar without a type checker, which a full descriptor grammar cannot. Since
   the whole point is cross-tool joining, the constraint is set by the weakest
   emitter.
2. **No package/module scheme prefix.** No `scip-java maven <group> <version>`
   header. These symbols are repo-local, not globally addressable.

**Remapping cost if we later align with L3.** The mapping from this grammar to
a full SCIP descriptor is one-directional and lossy at overloads only; every
other row maps mechanically. The remap is a single change in `symbolOf` plus a
re-run, since nothing else in the pack constructs symbols. Budget it as a wave-4
item if L3 claim symbols become the join key for the oracle comparison.

**What must not happen** is a third grammar appearing in the ast-grep rules. If
the ast-grep emitter cannot produce this grammar, change this document and
`symbolOf` together — do not let the emitters drift.
