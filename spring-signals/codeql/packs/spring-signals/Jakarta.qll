/**
 * Jakarta EE 9 namespace relocation: which `javax.*` packages moved, what they
 * moved to, and which look-alikes did NOT move.
 *
 * This lives in a library file, not inside JakartaMigration.ql, because the
 * boundary IS the bug surface: a review round added `jsr305Symbol` guards to
 * the query while `javax.annotation` was absent from `relocatedJavaxNamespace`,
 * which made the guards dead code and left `@PostConstruct` / `@Resource`
 * unflagged. A predicate buried in a `.ql` cannot be unit-tested; here it is
 * pinned by JakartaMigrationSanity.ql at the string level, exactly where the
 * boundary decisions live.
 */

/**
 * Holds if `pkg` is a `javax.*` namespace that Jakarta EE 9 relocated.
 *
 * The complement matters as much as the list: `javax.crypto`, `javax.net`,
 * `javax.sql`, `javax.naming`, `javax.management`, `javax.xml`,
 * `javax.security.auth`, `javax.imageio`, `javax.sound`, `javax.tools`,
 * `javax.script`, `javax.lang.model`, `javax.print`, `javax.accessibility`
 * and `javax.swing` are JDK-retained and MUST NOT be flagged. A naive
 * `^javax\.` rule produces a migration backlog full of false work.
 *
 * `javax.annotation` is a SPLIT namespace and gets its own alternative rather
 * than a slot in the main list, because the main list's `(\..*)?` continuation
 * would swallow the subpackages that did NOT move:
 *  - `javax.annotation.processing` is JDK-retained (javac API since Java 6).
 *  - `javax.annotation.concurrent` and `javax.annotation.meta` are JSR-305
 *    (com.google.code.findbugs:jsr305), which has no Jakarta equivalent.
 * Only the JSR-250 core (`@PostConstruct`, `@Resource`, `@Generated`, ...) and
 * its `security` / `sql` subpackages relocated to `jakarta.annotation`.
 */
bindingset[pkg]
predicate relocatedJavaxNamespace(string pkg) {
  pkg.regexpMatch("^javax\\.(persistence|validation|transaction|servlet|ws\\.rs|jms|mail|enterprise|inject|interceptor|json|batch|el|websocket|xml\\.bind|xml\\.soap|xml\\.ws|activation|security\\.enterprise|faces|resource)(\\..*)?$")
  or
  pkg.regexpMatch("^javax\\.annotation(\\.(security|sql)(\\..*)?)?$")
}

/** Gets the jakarta equivalent of a relocated javax namespace. */
bindingset[pkg]
string jakartaEquivalent(string pkg) {
  result = pkg.regexpReplaceAll("^javax\\.", "jakarta.")
}

/**
 * Holds if `fqn` is a JSR-305 symbol, which Jakarta EE 9 did NOT relocate.
 *
 * `javax.annotation` is a SPLIT namespace. The JSR-250 lifecycle annotations
 * (`@PostConstruct`, `@PreDestroy`, `@Resource`) moved to `jakarta.annotation`;
 * the JSR-305 nullness and concurrency annotations, which arrive transitively
 * via com.google.code.findbugs:jsr305, did not and have no jakarta equivalent.
 * Flagging them manufactures migration work that does not exist.
 *
 * The `concurrent` / `meta` entries are defence in depth: the
 * `relocatedJavaxNamespace` shape already excludes those subpackages, so this
 * predicate only ever fires for top-level `javax.annotation` symbols. If the
 * namespace boundary ever widens, this list is the second gate.
 */
bindingset[fqn]
predicate jsr305Symbol(string fqn) {
  fqn.regexpMatch("^javax\\.annotation\\.concurrent\\..*")
  or
  fqn in [
      "javax.annotation.Nullable", "javax.annotation.Nonnull",
      "javax.annotation.CheckReturnValue", "javax.annotation.CheckForNull",
      "javax.annotation.ParametersAreNonnullByDefault",
      "javax.annotation.ParametersAreNullableByDefault",
      "javax.annotation.OverridingMethodsMustInvokeSuper",
      "javax.annotation.WillClose", "javax.annotation.WillNotClose",
      "javax.annotation.Untainted", "javax.annotation.Tainted",
      "javax.annotation.MatchesPattern", "javax.annotation.Signed",
      "javax.annotation.Unsigned", "javax.annotation.Nonnegative",
      "javax.annotation.RegEx", "javax.annotation.Syntax",
      "javax.annotation.PropertyKey", "javax.annotation.meta.When"
    ]
}
