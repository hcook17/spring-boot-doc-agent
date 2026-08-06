/**
 * @name JPA persistence surface
 * @description Entities, repositories, and mapping annotations.
 *
 * P0 fixes vs the previous version:
 *   1. `getASupertype()` -> transitive `getASourceSupertype*()`. The old
 *      one-hop walk missed four repositories in ocs-api-service
 *      (BookBasedTopic/Concept/Lesson/ModuleRepository, each extending another
 *      repository interface rather than CrudRepository directly).
 *   2. `getTableName` is now total. The old `any(...)` construction had NO
 *      result for a `@Table` carrying `schema` but not `name`, which deleted
 *      the entire entity row rather than defaulting the table name.
 *   3. `StringLiteral` -> `CompileTimeConstantExpr`, so constant-reference
 *      attribute values are read rather than dropped.
 *   4. Entity type argument is resolved on the parameterized ancestor that
 *      actually binds it, not on the direct supertype.
 *
 * @kind table
 * @id spring-signals/persistence
 * @tags persistence
 */

import _Common

/** Gets the declared table name of `c`, or "" when unset. Total by construction. */
private string tableNameOf(Class c) {
  result =
    concat(Annotation a |
      a = getAnEffectiveAnnotation(c) and
      exists(string pkg | isExactly(a, pkg, "Table") and signature("jpa", pkg, "Table", _, _))
    |
      attr(a, "name"), "|"
    )
}

/** Gets the declared schema of `c`, or "" when unset. */
private string schemaOf(Class c) {
  result =
    concat(Annotation a |
      a = getAnEffectiveAnnotation(c) and
      exists(string pkg | isExactly(a, pkg, "Table") and signature("jpa", pkg, "Table", _, _))
    |
      attr(a, "schema"), "|"
    )
}

from Measured e, string rule_id, string generation, string signal, string detail
where
  // Entity classes. `signal` is the class, `detail` is schema-qualified table.
  exists(Class c, Annotation a, string pkg |
    e = c and
    a = getAnEffectiveAnnotation(c) and
    isExactly(a, pkg, "Entity") and
    signature("jpa", pkg, "Entity", _, generation) and
    signal = sym(c) and
    detail = schemaOf(c) + "." + tableNameOf(c) and
    rule_id = "persistence__entity"
  )
  or
  // Spring Data repositories, via a TRANSITIVE supertype walk.
  exists(Interface i, RefType root, string pkg, string name |
    e = i and
    repositoryRoot(pkg, name, generation) and
    root = sourceDeclOf(i).getASourceSupertype*() and
    root.hasQualifiedName(pkg, name) and
    signal = sym(i) and
    detail =
      concat(Type arg | arg = boundTypeArgument(i, pkg, name, 0) | typeName(arg), "|") + " <- " +
        pkg + "." + name and
    rule_id = "persistence__repository"
  )
  or
  // Repository tagging interfaces.
  //
  // RULE (all four conditions, deliberately narrow):
  //   1. `i` is a Spring Data repository -- it reaches a catalogued repository
  //      root through the transitive supertype walk.
  //   2. `marker` is a DIRECT supertype of `i`.
  //   3. `marker` declares no methods and no fields, and is not itself a
  //      catalogued repository root.
  //   4. `marker` is declared in first-party source.
  //
  // Conditions 3 and 4 are what keep this from becoming "interfaces I find
  // interesting". A marker that declares even one method is a repository
  // fragment (Spring Data's custom-implementation mechanism) and belongs to a
  // different rule; a marker from a dependency is not this repo's architecture.
  //
  // On ocs-api-service this yields exactly the four BookBased*Repository types
  // tagged with `BookBasedRepository`, which is a runtime repository-selection
  // mechanism with no annotation anywhere to detect it.
  exists(Interface i, Interface marker |
    e = i and
    marker = sourceDeclOf(i).getASourceSupertype() and
    exists(sourceSetOf(marker.getFile())) and
    not exists(Method m | m = marker.getAMethod()) and
    not exists(Field f | f = marker.getAField()) and
    not exists(string p, string n | repositoryRoot(p, n, _) and marker.hasQualifiedName(p, n)) and
    exists(string p, string n |
      repositoryRoot(p, n, _) and
      sourceDeclOf(i).getASourceSupertype*().hasQualifiedName(p, n)
    ) and
    signal = sym(i) and
    detail = sym(marker) and
    generation = "" and
    rule_id = "persistence__repository_marker"
  )
  or
  // Mapping annotations, generation-tagged so the javax/jakarta split is
  // visible without a separate join.
  exists(Annotatable owner, Annotation a, string pkg, string name, string kind |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    isExactly(a, pkg, name) and
    signature("jpa", pkg, name, kind, generation) and
    kind in ["column", "join", "relation", "id", "locking", "mapping", "lifecycle", "table"] and
    signal = pkg + "." + name and
    detail = attr(a, "name") and
    rule_id = "persistence__" + kind
  )
  or
  // @Transactional, all three namespaces.
  exists(Annotatable owner, Annotation a, string pkg |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    (
      isExactly(a, pkg, "Transactional") and
      signature("jpa", pkg, "Transactional", "transactional", generation)
      or
      isExactly(a, "org.springframework.transaction.annotation", "Transactional") and
      pkg = "org.springframework.transaction.annotation" and
      generation = ""
    ) and
    signal = pkg + ".Transactional" and
    detail = attr(a, "propagation") + attr(a, "readOnly") and
    rule_id = "persistence__transactional"
  )
select
  e.getPath() as file,
  e.getStartLine() as start_line,
  e.getEndLine() as end_line,
  e.getSourceSet() as source_set,
  schemaVersion() as schema_version,
  rule_id,
  "jpa" as framework,
  generation,
  sym(e) as symbol,
  signal,
  detail
