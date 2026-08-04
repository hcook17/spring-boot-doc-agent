/**
 * @name javax to jakarta namespace burndown
 * @description Every first-party reference to a `javax.*` namespace that moved
 *              to `jakarta.*` in Jakarta EE 9, plus the `jakarta.*` references
 *              already migrated. The ratio is the Boot 2.7 -> 3.0 burndown.
 *              ocs-api-service: 297 javax imports, 286 of them javax.persistence.
 * @kind table
 * @id spring-signals/jakarta-migration
 * @tags migration jakarta
 */

import Common

/**
 * Holds if `fqn` is a JSR-305 symbol, which Jakarta EE 9 did NOT relocate.
 *
 * `javax.annotation` is a SPLIT namespace. The JSR-250 lifecycle annotations
 * (`@PostConstruct`, `@PreDestroy`, `@Resource`) moved to `jakarta.annotation`;
 * the JSR-305 nullness and concurrency annotations, which arrive transitively
 * via com.google.code.findbugs:jsr305, did not and have no jakarta equivalent.
 * Flagging them manufactures migration work that does not exist -- the failure
 * the namespace enumeration above exists to prevent, reintroduced one level
 * down because the split is inside a package, not between packages.
 */
bindingset[fqn]
private predicate jsr305Symbol(string fqn) {
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

/**
 * Holds if `pkg` is a `javax.*` namespace that Jakarta EE 9 relocated.
 *
 * The complement matters as much as the list: `javax.crypto`, `javax.net`,
 * `javax.sql`, `javax.naming`, `javax.management`, `javax.xml`,
 * `javax.security.auth`, `javax.imageio`, `javax.sound`, `javax.tools`,
 * `javax.script`, `javax.lang.model`, `javax.print`, `javax.accessibility`
 * and `javax.swing` are JDK-retained and MUST NOT be flagged. A naive
 * `^javax\.` rule produces a migration backlog full of false work.
 */
bindingset[pkg]
private predicate relocatedJavaxNamespace(string pkg) {
  pkg.regexpMatch("^javax\\.(persistence|validation|transaction|servlet|ws\\.rs|jms|mail|enterprise|inject|interceptor|json|batch|el|websocket|xml\\.bind|xml\\.soap|xml\\.ws|activation|security\\.enterprise|faces|resource)(\\..*)?$")
}

/** Gets the jakarta equivalent of a relocated javax namespace. */
bindingset[pkg]
private string jakartaEquivalent(string pkg) {
  result = pkg.regexpReplaceAll("^javax\\.", "jakarta.")
}

from Measured e, string rule_id, string generation, string signal, string detail
where
  // -- Import declarations.
  exists(ImportType imp, string pkg |
    e = imp and
    pkg = imp.getImportedType().getSourceDeclaration().getPackage().getName() and
    signal = pkg + "." + imp.getImportedType().getSourceDeclaration().getName() and
    (
      relocatedJavaxNamespace(pkg) and
      not jsr305Symbol(signal) and
      generation = "javax" and
      rule_id = "jakarta__pending_import" and
      detail = jakartaEquivalent(signal)
      or
      pkg.regexpMatch("^jakarta\\..*") and
      generation = "jakarta" and
      rule_id = "jakarta__migrated_import" and
      detail = ""
    )
  )
  or
  // -- Annotation uses. Caught independently of imports because a fully
  // -- qualified inline annotation leaves no Import node at all.
  exists(Annotatable owner, Annotation a, string pkg |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    pkg = a.getType().getSourceDeclaration().getPackage().getName() and
    signal = annotationFqn(a) and
    (
      relocatedJavaxNamespace(pkg) and
      not jsr305Symbol(signal) and
      generation = "javax" and
      rule_id = "jakarta__pending_annotation" and
      detail = jakartaEquivalent(signal)
      or
      pkg.regexpMatch("^jakarta\\..*") and
      generation = "jakarta" and
      rule_id = "jakarta__migrated_annotation" and
      detail = ""
    )
  )
  or
  // -- Type references in declarations (fields, params, locals, returns).
  // -- Catches `javax.persistence.EntityManager em` written fully qualified.
  exists(Variable v, string pkg |
    e = v and
    pkg = sourceDeclOf(v.getType()).getPackage().getName() and
    signal = typeFqn(v.getType()) and
    (
      relocatedJavaxNamespace(pkg) and
      not jsr305Symbol(signal) and
      generation = "javax" and
      rule_id = "jakarta__pending_type" and
      detail = jakartaEquivalent(signal)
      or
      pkg.regexpMatch("^jakarta\\..*") and
      generation = "jakarta" and
      rule_id = "jakarta__migrated_type" and
      detail = ""
    )
  )
  or
  // -- Return types. Variable does not cover them, so add a Method branch.
  exists(Method m, string pkg |
    e = m and
    pkg = sourceDeclOf(m.getReturnType()).getPackage().getName() and
    signal = typeFqn(m.getReturnType()) and
    (
      relocatedJavaxNamespace(pkg) and
      not jsr305Symbol(signal) and
      generation = "javax" and
      rule_id = "jakarta__pending_type" and
      detail = jakartaEquivalent(signal)
      or
      pkg.regexpMatch("^jakarta\\..*") and
      generation = "jakarta" and
      rule_id = "jakarta__migrated_type" and
      detail = ""
    )
  )
select
  e.getPath() as file,
  e.getStartLine() as start_line,
  e.getEndLine() as end_line,
  e.getSourceSet() as source_set,
  schemaVersion() as schema_version,
  rule_id,
  "jakarta" as framework,
  generation,
  sym(e) as symbol,
  signal,
  detail
