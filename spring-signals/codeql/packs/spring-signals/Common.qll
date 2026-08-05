/** Shared imports and helpers for every spring-signals query. */

import java
import signals.Schema
import signals.Annotations
import signals.Types
import Catalog
// Brings Spring's MetaAnnotationEdges contribution into scope. An abstract class
// only has effect where a subclass is in the import closure, so dropping this
// import silently reopens the @RestController recall regression.
import SpringMetaEdges

/**
 * Gets the single-valued text of an optional annotation attribute, or "" when
 * absent or non-constant.
 *
 * `concat` over an empty row set yields "", which makes this total. Totality
 * matters: a non-total helper used in a `where` clause silently deletes the
 * whole row. That is exactly how the old `getTableName` predicate would drop an
 * entire `persistence__entity` row for any `@Table` lacking a `name` attribute.
 */
bindingset[name]
string attr(Annotation a, string name) {
  result =
    concat(string s |
      s = constantString(a.getValue(name))
      or
      s = constantString(a.getValue(name).(ArrayInit).getAnInit())
    |
      s, "|" order by s
    )
}

/**
 * Gets the values of the attributes named in `names` (comma-separated), joined
 * with "|" in the order given, skipping absent ones.
 *
 * Five call sites had grown their own inline
 * `concat(string s | s = attr(a, "x") and s != "" or ... | s, SEP order by s)`,
 * with THREE different separators -- "" in ApiSurface.mappingPath and
 * Configuration's prefix/value, " " in OpenApiSurface, "|" in Messaging and
 * Configuration's basePackages -- and lexicographic ordering everywhere, so the
 * output order does not follow the attribute order the reader sees. A consumer
 * cannot split a "" join at all, and cannot rely on position in the others.
 *
 * One separator, call-site order. AliasFor pairs (`value`/`path`,
 * `prefix`/`value`, `value`/`url`, `value`/`basePackages`) are NOT joins --
 * use `attrFallback` for those.
 */
bindingset[names]
string attrs(Annotation a, string names) {
  result =
    concat(int i, string v |
      v = attr(a, names.splitAt(",", i)) and v != ""
    |
      v, "|" order by i
    )
}

/**
 * Gets the first non-empty value among the attributes named in `names`.
 *
 * For `@AliasFor` pairs -- `@ConfigurationProperties(prefix=)` / `(value=)`,
 * `@RequestMapping(value=)` / `(path=)` -- Spring guarantees at most one is set,
 * so the correct operation is a fallback, not a join. Joining them would put a
 * "|" into `signal`, which Schema.qll documents as a single identity value.
 */
bindingset[names]
string attrFallback(Annotation a, string names) {
  result =
    min(int i, string v |
      v = attr(a, names.splitAt(",", i)) and v != ""
    |
      v order by i
    )
  or
  not exists(string v | v = attr(a, names.splitAt(",", _)) and v != "") and result = ""
}

/**
 * Gets the stable symbol for `e`.
 *
 * Thin alias for `Schema::symbolOf` so that no query ever hand-rolls a symbol
 * string. See docs/SYMBOLS.md.
 */
string sym(Element e) { result = min(string s | s = symbolOf(e) | s) }

/**
 * Holds if `symbolOf` is not single-valued for `e`.
 *
 * `sym` uses `min` rather than `concat` deliberately. A `concat` fallback would
 * silently synthesise a composite key like `A#foo().|B#bar().` the first time
 * `symbolOf` returned two results, and every join on (file, symbol, rule_id)
 * would degrade without failing. `min` keeps the key well-formed; this
 * predicate makes the underlying ambiguity observable instead of hidden.
 *
 * Diagnostic only. `symbolOf` is single-valued by construction (declSymbol
 * branches are disjoint, ownerSymbol is constrained by type, and the file tier
 * is unique), so this predicate is empty on every database. It survives as a
 * canary: if a future change to `symbolOf` makes it multi-valued, this row
 * count will become non-zero. Do not list it as a merge-blocking exit criterion.
 */
predicate ambiguousSymbol(Measured e) { count(symbolOf(e)) > 1 }

/**
 * Holds if `symbolOf` yields nothing for a first-party element.
 *
 * The mirror of `ambiguousSymbol`, and the more dangerous of the two. `sym`
 * appears in every `select`, so a MISSING symbol deletes the row outright --
 * silently, with no error and no blank column. An earlier `symbolOf` resolved
 * annotations only when the annotated element was a `RefType`, which would have
 * dropped most annotation rows and every JakartaMigration import row.
 *
 * `symbolOf`'s file-path tier makes this unsatisfiable by construction. It is
 * no longer an exit criterion; it survives as a structural sanity check that
 * can be inspected if a future change to `symbolOf` reintroduces a gap.
 */
predicate unresolvedSymbol(Measured e) { not exists(symbolOf(e)) }
