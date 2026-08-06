/**
 * @name javax to jakarta namespace burndown
 * @description First-party references to a `javax.*` namespace that moved to
 *              `jakarta.*` in Jakarta EE 9, plus the `jakarta.*` references
 *              already migrated. The ratio is the Boot 2.7 -> 3.0 burndown.
 *              ocs-api-service: 297 javax imports, 286 of them javax.persistence.
 *
 *              Covered reference shapes: import declarations (single-type and
 *              on-demand), annotation uses (direct, meta-resolved, repeatable
 *              containers, and fully qualified inline, which leaves no Import
 *              node), declared types of fields/parameters/locals/return types,
 *              parameterized type arguments (`List<javax.persistence.Entity>`),
 *              and class literals (`Entity.class`). NOT covered: static
 *              imports, `throws` clauses, and extends/implements clauses --
 *              enumerate before claiming, rather than claiming "every".
 * @kind table
 * @id spring-signals/jakarta-migration
 * @tags migration jakarta
 */

import Common
import Jakarta

/**
 * Classifies a referenced `pkg`/`signal` pair as pending or migrated for the
 * given `kind` ("import" | "annotation" | "type"). Shared by every arm so the
 * relocation/JSR-305 decision lives in exactly one place.
 */
// bindingset: callers always supply kind/pkg/signal. Without it the compiler
// requires an in-body binding occurrence for each parameter, and the only
// occurrences here (bindingset callees, regexpMatch, inputs to `+`) bind none.
bindingset[kind, pkg, signal]
private predicate migrationRow(string kind, string pkg, string signal, string rule_id, string generation, string detail) {
  relocatedJavaxNamespace(pkg) and
  not jsr305Symbol(signal) and
  generation = "javax" and
  rule_id = "jakarta__pending_" + kind and
  detail = jakartaEquivalent(signal)
  or
  pkg.regexpMatch("^jakarta\\..*") and
  generation = "jakarta" and
  rule_id = "jakarta__migrated_" + kind and
  detail = ""
}

from Measured e, string rule_id, string generation, string signal, string detail
where
  // -- Import declarations.
  exists(ImportType imp, string pkg |
    e = imp and
    pkg = imp.getImportedType().getSourceDeclaration().getPackage().getName() and
    signal = pkg + "." + imp.getImportedType().getSourceDeclaration().getName() and
    migrationRow("import", pkg, signal, rule_id, generation, detail)
  )
  or
  // -- On-demand imports. `import javax.persistence.*` leaves no per-type
  // -- ImportType node; signal is the package with a ".*" suffix. The split
  // -- namespaces are per-symbol, so a `javax.annotation.*` row cannot tell
  // -- JSR-250 from JSR-305 -- the annotation arm prices uses precisely; this
  // -- row records that the namespace is referenced at all.
  exists(ImportOnDemandFromPackage imp, string pkg |
    e = imp and
    pkg = imp.getPackageHoldingImport().getName() and
    signal = pkg + ".*" and
    migrationRow("import", pkg, signal, rule_id, generation, detail)
  )
  or
  // -- Annotation uses. Caught independently of imports because a fully
  // -- qualified inline annotation leaves no Import node at all.
  exists(Annotatable owner, Annotation a, string pkg |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    pkg = a.getType().getSourceDeclaration().getPackage().getName() and
    signal = annotationFqn(a) and
    migrationRow("annotation", pkg, signal, rule_id, generation, detail)
  )
  or
  // -- Type references in declarations (fields, params, locals, returns).
  // -- Catches `javax.persistence.EntityManager em` written fully qualified.
  exists(Variable v, string pkg |
    e = v and
    pkg = sourceDeclOf(v.getType()).getPackage().getName() and
    signal = typeFqn(v.getType()) and
    migrationRow("type", pkg, signal, rule_id, generation, detail)
  )
  or
  // -- Return types. Variable does not cover them, so add a Method branch.
  exists(Method m, string pkg |
    e = m and
    pkg = sourceDeclOf(m.getReturnType()).getPackage().getName() and
    signal = typeFqn(m.getReturnType()) and
    migrationRow("type", pkg, signal, rule_id, generation, detail)
  )
  or
  // -- Parameterized type arguments. `List<javax.persistence.Entity>` declares
  // -- a java.util type; the javax reference lives one level down.
  exists(Variable v, Type arg, string pkg |
    e = v and
    arg = v.getType().(ParameterizedType).getATypeArgument() and
    pkg = sourceDeclOf(arg).getPackage().getName() and
    signal = typeFqn(arg) and
    migrationRow("type", pkg, signal, rule_id, generation, detail)
  )
  or
  exists(Method m, Type arg, string pkg |
    e = m and
    arg = m.getReturnType().(ParameterizedType).getATypeArgument() and
    pkg = sourceDeclOf(arg).getPackage().getName() and
    signal = typeFqn(arg) and
    migrationRow("type", pkg, signal, rule_id, generation, detail)
  )
  or
  // -- Class literals: `Entity.class`.
  exists(TypeLiteral lit, string pkg |
    e = lit and
    pkg = sourceDeclOf(lit.getReferencedType()).getPackage().getName() and
    signal = typeFqn(lit.getReferencedType()) and
    migrationRow("type", pkg, signal, rule_id, generation, detail)
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
