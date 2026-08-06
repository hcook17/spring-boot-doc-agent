/** Shared imports and helpers for every spring-signals query. */

import java
import signals.Schema
import signals.Annotations
import signals.Types
import signals.Catalog

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
      s, "|"
    )
}

/**
 * Gets the stable symbol for `e`.
 *
 * Thin alias for `Schema::symbolOf` so that no query ever hand-rolls a symbol
 * string. See docs/SYMBOLS.md.
 */
string sym(Element e) { result = concat(string s | s = symbolOf(e) | s, "|") }
