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
 * 1a exit criterion: `select count(Element e | ambiguousSymbol(e))` is 0 on
 * ocs-api-service. If it is not, fix `symbolOf` -- do not widen `sym`.
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
 * asserted anyway, because "unsatisfiable by construction" is what the previous
 * version also looked like.
 *
 * 1a exit criterion: `unresolved_symbols = 0`.
 */
predicate unresolvedSymbol(Measured e) { not exists(symbolOf(e)) }
