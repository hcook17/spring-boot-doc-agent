/**
 * @name Hibernate 5 to 6 blockers
 * @description Hibernate-specific mapping annotations whose semantics changed
 *              or which were renamed between Hibernate ORM 5.x (Boot 2.7) and
 *              6.x (Boot 3.0+), plus use of the hibernate-types-52 library that
 *              Hibernate 6 supersedes with hypersistence-utils.
 *              ocs-api-service: 15 @Type, 12 @TypeDef, plus @Where/@Fetch/
 *              @GenericGenerator, backed by com.vladmihalcea:hibernate-types-52.
 * @kind table
 * @id spring-signals/hibernate-types
 * @tags migration hibernate persistence
 */

import _Common

from Measured e, string rule_id, string generation, string signal, string detail
where
  // -- Hibernate mapping annotations, generation-tagged from the catalog.
  exists(Annotatable owner, Annotation a, string pkg, string name, string kind |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    isExactly(a, pkg, name) and
    signature("hibernate", pkg, name, kind, generation) and
    signal = pkg + "." + name and
    detail = kind and
    rule_id = "hibernate__" + kind
  )
  or
  // -- hibernate-types-52 type references. `@Type(type = "jsonb")` plus
  // -- `@TypeDef(typeClass = JsonBinaryType.class)` is the classic pairing;
  // -- both sides need rewriting to `@JdbcTypeCode(SqlTypes.JSON)` on
  // -- Hibernate 6, so both sides are reported.
  exists(TypeAccess ta |
    e = ta and
    typePackageMatches(ta.getType(), "^com\\.vladmihalcea\\..*") and
    signal = typeFqn(ta.getType()) and
    generation = "hibernate5" and
    detail = "replace with hypersistence-utils or @JdbcTypeCode" and
    rule_id = "hibernate__legacy_types_library"
  )
  or
  exists(ImportType imp |
    e = imp and
    imp.getImportedType().getSourceDeclaration().getPackage().getName().regexpMatch("^com\\.vladmihalcea\\..*") and
    signal =
      imp.getImportedType().getSourceDeclaration().getPackage().getName() + "." +
        imp.getImportedType().getSourceDeclaration().getName() and
    generation = "hibernate5" and
    detail = "replace with hypersistence-utils or @JdbcTypeCode" and
    rule_id = "hibernate__legacy_types_import"
  )
select
  e.getPath() as file,
  e.getStartLine() as start_line,
  e.getEndLine() as end_line,
  e.getSourceSet() as source_set,
  schemaVersion() as schema_version,
  rule_id,
  "hibernate" as framework,
  generation,
  sym(e) as symbol,
  signal,
  detail
