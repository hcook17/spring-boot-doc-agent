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
 * `javax.imageio`, `javax.sound`, `javax.tools`,
 * `javax.script`, `javax.lang.model`, `javax.print`, `javax.accessibility`,
 * `javax.swing`, and `javax.transaction.xa` (JDK-retained JTA; see the
 * transaction split below) are JDK-retained and MUST NOT be flagged. A naive
 * `^javax\.` rule produces a migration backlog full of false work.
 *
 * `javax.security.auth` is itself a SPLIT namespace: the core is JDK-retained
 * (JAAS, in Java SE since 1.4), but two subtrees relocated with Jakarta EE 9 --
 * `javax.security.auth.message` -> `jakarta.security.auth.message` (JASPIC /
 * Jakarta Authentication) and `javax.security.jacc` -> `jakarta.security.jacc`
 * (JACC / Jakarta Authorization). They get explicit alternatives below, ahead
 * of any reading of "javax.security.auth is JDK-retained" as covering them.
 *
 * `javax.transaction` is the same shape in reverse: the EE JTA API relocated
 * to `jakarta.transaction`, but `javax.transaction.xa` (XAResource, Xid,
 * XAException) ships in the JDK's `java.transaction.xa` module and must NOT
 * be flagged. A bare `transaction` slot in the main alternation would swallow
 * `.xa` via `(\..*)?` -- the exact false-positive this PR's earlier boundary
 * work was meant to prevent. It has its own alternative below, matching the
 * security.auth pattern.
 *
 * Source of truth for the boundary: jakartaee/jakartaee-platform,
 * namespace/mappings.adoc AND namespace/unaffected-packages.adoc (cross-check
 * both -- mappings.adoc alone is explicitly "tentative" on some rows). The
 * list is deliberately exhaustive rather than a prefix heuristic -- see the
 * Jackson note in Catalog.qll for why.
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
  // cache: javax.cache -> jakarta.cache (JSR-107 / JCache), fully listed in
  // mappings.adoc. Absent from both this list and the retained docstring it
  // fell through both buckets -- a silent false negative.
  pkg.regexpMatch("^javax\\.(persistence|validation|servlet|ws\\.rs|jms|mail|enterprise|inject|interceptor|json|batch|el|websocket|xml\\.bind|xml\\.soap|xml\\.ws|activation|security\\.enterprise|faces|resource|ejb|decorator|jws|jsp|cache)(\\..*)?$")
  or
  // javax.transaction relocated EXCEPT javax.transaction.xa, which is
  // JDK-retained JTA (java.transaction.xa module). Source: mappings.adoc
  // ("excluding javax.transaction.xa which is still part of JavaSE") and
  // unaffected-packages.adoc.
  pkg.regexpMatch("^javax\\.transaction(\\..*)?$") and
  not pkg.regexpMatch("^javax\\.transaction\\.xa(\\..*)?$")
  or
  pkg.regexpMatch("^javax\\.annotation(\\.(security|sql)(\\..*)?)?$")
  or
  // Relocated subtrees of the otherwise JDK-retained javax.security.auth.
  pkg.regexpMatch("^javax\\.security\\.auth\\.message(\\..*)?$")
  or
  pkg.regexpMatch("^javax\\.security\\.jacc(\\..*)?$")
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
 * The top-level list below is derived from the actual artifact contents of
 * com.google.code.findbugs:jsr305:3.0.2 (the version the fixture pins in
 * deps.txt): every top-level `javax.annotation` class in that jar is listed,
 * and nothing else -- an earlier draft carried `Unsigned`, which does not
 * exist in the jar, and missed `CheckForSigned`, `Detainted` and
 * `WillCloseWhenClosed`, which do. A symbol absent from this list but present
 * in a scanned repo is flagged as pending migration work that does not exist.
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
      "javax.annotation.CheckForSigned",
      "javax.annotation.ParametersAreNonnullByDefault",
      "javax.annotation.ParametersAreNullableByDefault",
      "javax.annotation.OverridingMethodsMustInvokeSuper",
      "javax.annotation.WillClose", "javax.annotation.WillCloseWhenClosed",
      "javax.annotation.WillNotClose",
      "javax.annotation.Untainted", "javax.annotation.Detainted",
      "javax.annotation.Tainted",
      "javax.annotation.MatchesPattern", "javax.annotation.Signed",
      "javax.annotation.Nonnegative",
      "javax.annotation.RegEx", "javax.annotation.Syntax",
      "javax.annotation.PropertyKey", "javax.annotation.meta.When"
    ]
}
