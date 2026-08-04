/**
 * @name SQL and JPQL execution surface
 * @description Every place this service emits a query string: Spring Data
 *              `@Query`, JPA `@NamedNativeQuery`/`@NamedQuery`, and JdbcTemplate
 *              call sites. Supersedes RawQueries.ql, which saw only the first of
 *              the three (198 of ~250 sites in ocs-api-service) and extracted no
 *              structure from the SQL it did see.
 * @kind table
 * @id spring-signals/native-sql
 * @tags sql persistence migration
 */

import Common

/** Gets the query text carried by a Spring Data `@Query` annotation. */
private string springDataQueryText(Annotation a) {
  result = normalizeWhitespace(concatenatedText(a.getValue("value")))
}

/** Holds if a Spring Data `@Query` is explicitly marked native. */
private predicate isNativeQuery(Annotation a) {
  constantBoolean(a.getValue("nativeQuery")) = true
}

/**
 * Gets a schema-qualified table reference from `sql`.
 *
 * ocs-api-service addresses two Postgres schemas explicitly (`content.`,
 * `evolve.`). Capturing them turns this query into a Java-to-schema dependency
 * map, which is the artifact that makes the pack worth running.
 */
bindingset[sql]
private string schemaRefs(string sql) {
  result =
    concat(string s |
      s = sql.regexpFind("(?i)\\b(content|evolve|public)\\.[a-z_][a-z0-9_]*", _, _)
    |
      s.toLowerCase(), "," order by s.toLowerCase()
    )
}

/** Holds if `sql` uses a Postgres JSON/JSONB operator or function. */
bindingset[sql]
private boolean usesJson(string sql) {
  sql.regexpMatch("(?is).*(->>|->|#>>|jsonb_|json_build_object|jsonb_array_elements).*") and result = true
  or
  not sql.regexpMatch("(?is).*(->>|->|#>>|jsonb_|json_build_object|jsonb_array_elements).*") and result = false
}

from
  Measured e, string rule_id, string generation, string signal, string sql
where
  // -- Spring Data @Query on a repository method.
  exists(Method m, Annotation a |
    e = a and
    m.getAnAnnotation() = a and
    isOrMeta(a, "org.springframework.data.jpa.repository", "Query") and
    sql = springDataQueryText(a) and
    signal = annotationFqn(a) and
    generation = "" and
    (
      isNativeQuery(a) and rule_id = "sql__data_query_native"
      or
      not isNativeQuery(a) and rule_id = "sql__data_query_jpql"
    )
  )
  or
  // -- Spring Data JPA 3.4+ @NativeQuery. Absent on Boot 2.7; present here so
  // -- the burndown has a target column once the migration lands.
  exists(Method m, Annotation a |
    e = a and
    m.getAnAnnotation() = a and
    isOrMeta(a, "org.springframework.data.jpa.repository", "NativeQuery") and
    sql = normalizeWhitespace(concatenatedText(a.getValue("value"))) and
    signal = annotationFqn(a) and
    generation = "boot3+" and
    rule_id = "sql__data_query_native"
  )
  or
  // -- JPA @NamedNativeQuery / @NamedQuery, including repeatable containers.
  // -- 9 @NamedNativeQuery + 8 @SqlResultSetMapping in ocs-api-service, all of
  // -- it native SQL that a @Query-only rule cannot see.
  exists(Annotatable owner, Annotation a, string pkg |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    isExactly(a, pkg, "NamedNativeQuery") and
    signature("jpa", pkg, "NamedNativeQuery", _, generation) and
    sql = normalizeWhitespace(concatenatedText(a.getValue("query"))) and
    signal = attr(a, "name") and
    rule_id = "sql__named_native_query"
  )
  or
  exists(Annotatable owner, Annotation a, string pkg |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    isExactly(a, pkg, "NamedQuery") and
    signature("jpa", pkg, "NamedQuery", _, generation) and
    sql = normalizeWhitespace(concatenatedText(a.getValue("query"))) and
    signal = attr(a, "name") and
    rule_id = "sql__named_jpql_query"
  )
  or
  // -- JdbcTemplate / NamedParameterJdbcTemplate / EntityManager call sites.
  exists(MethodCall call, string pkg, string name |
    e = call and
    sqlExecutorType(pkg, name, generation) and
    typeIsOrExtends(call.getReceiverType(), pkg, name) and
    signal = name + "." + call.getMethod().getName() and
    // `Argument` is not a class in the Java library and `Expr` has no
    // getPosition(); index through getArgument(i) instead. The index also gives
    // the concat a deterministic order, which arg-set iteration would not.
    sql =
      normalizeWhitespace(concat(int i, Expr arg |
          arg = call.getArgument(i) and arg.getType() instanceof TypeString
        |
          concatenatedText(arg), " " order by i
        )) and
    rule_id = "sql__jdbc_call"
  )
select
  e.getPath() as file,
  e.getStartLine() as start_line,
  e.getEndLine() as end_line,
  e.getSourceSet() as source_set,
  schemaVersion() as schema_version,
  rule_id,
  "sql" as framework,
  generation,
  sym(e) as symbol,
  signal,
  sql as detail,
  schemaRefs(sql) as schema_refs,
  usesJson(sql) as uses_json
