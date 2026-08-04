/**
 * @name Spring HTTP API surface
 * @description Controllers and request mappings, separating class-level path
 *              prefixes from method-level endpoints and extracting the declared
 *              path. The previous version emitted one undifferentiated
 *              `api_surface__mapping` for both, so 35 class-level prefixes in
 *              ocs-api-service were indistinguishable from the 369 real
 *              endpoints and no endpoint count could be reconstructed.
 * @kind table
 * @id spring-signals/api-surface
 * @tags api
 */

import Common

/** Holds if `a` is a Spring request-mapping annotation of the given `kind`. */
private predicate mappingAnnotation(Annotation a, string kind) {
  exists(string name |
    isExactly(a, "org.springframework.web.bind.annotation", name) and
    signature("spring", "org.springframework.web.bind.annotation", name, kind, _) and
    kind.matches("mapping_%")
  )
}

/** Holds if `a` is a parameter-binding annotation with simple name `name`. */
private predicate paramBindingAnnotation(Annotation a, string name) {
  isExactly(a, "org.springframework.web.bind.annotation", name) and
  signature("spring", "org.springframework.web.bind.annotation", name, "param_binding", _)
}

/** Gets the HTTP method implied by a mapping annotation. */
private string httpMethod(Annotation a, string kind) {
  kind = "mapping_get" and result = "GET"
  or
  kind = "mapping_post" and result = "POST"
  or
  kind = "mapping_put" and result = "PUT"
  or
  kind = "mapping_patch" and result = "PATCH"
  or
  kind = "mapping_delete" and result = "DELETE"
  or
  kind = "mapping_any" and
  result =
    concat(FieldAccess fa |
      fa = a.getValue("method").getAChildExpr*() and
      fa.getField().getDeclaringType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestMethod")
    |
      fa.getField().getName(), "|" order by fa.getField().getName()
    )
}

/** Gets the declared path of a mapping annotation, or "" if none. */
private string mappingPath(Annotation a) {
  result = concat(string s | s = attr(a, "value") and s != "" or s = attr(a, "path") and s != "" | s, "" order by s)
}

/** Gets the binding name: explicit value if present, else the inferred name. */
private string paramBindingDetail(Annotation a) {
  attr(a, "value") != "" and result = attr(a, "value")
  or
  attr(a, "value") = "" and result = attr(a, "name")
}

from Measured e, string rule_id, string signal, string detail
where
  // Controller classes, resolved through meta-annotations so @RestController
  // (meta @Controller) and any project-local composed stereotype both land.
  exists(Class c, Annotation a |
    e = a and
    a = getAnEffectiveAnnotation(c) and
    isOrMeta(a, "org.springframework.stereotype", "Controller") and
    signal = annotationFqn(a) and
    detail = "" and
    rule_id = "api_surface__controller"
  )
  or
  // Class-level mapping: a path prefix, not an endpoint.
  exists(Class c, Annotation a, string kind |
    e = a and
    a = getAnEffectiveAnnotation(c) and
    mappingAnnotation(a, kind) and
    signal = annotationFqn(a) and
    detail = concat(string s, int order | (s = httpMethod(a, kind) and order = 1 and s != "") or (s = mappingPath(a) and order = 2 and s != "") | s, " " order by order) and
    rule_id = "api_surface__path_prefix"
  )
  or
  // Method-level mapping: the actual endpoints.
  exists(Method m, Annotation a, string kind |
    e = a and
    a = getAnEffectiveAnnotation(m) and
    mappingAnnotation(a, kind) and
    signal = annotationFqn(a) and
    detail = concat(string s, int order | (s = httpMethod(a, kind) and order = 1 and s != "") or (s = mappingPath(a) and order = 2 and s != "") | s, " " order by order) and
    rule_id = "api_surface__endpoint"
  )
  or
  // Parameter binding. `@RequestParam` / `@PathVariable` without an explicit
  // name depend on `-parameters` reaching javac; Spring 6.1 stopped falling back
  // to debug symbols, which is the most common Boot 3.2 upgrade break. `detail`
  // is the declared name, so an EMPTY detail on these rows is the finding.
  exists(Parameter p, Annotation a, string name |
    e = a and
    a = getAnEffectiveAnnotation(p) and
    paramBindingAnnotation(a, name) and
    signal = annotationFqn(a) and
    detail = paramBindingDetail(a) and
    rule_id = "api_surface__param_binding"
  )
select
  e.getPath() as file,
  e.getStartLine() as start_line,
  e.getEndLine() as end_line,
  e.getSourceSet() as source_set,
  schemaVersion() as schema_version,
  rule_id,
  "spring" as framework,
  "" as generation,
  sym(e) as symbol,
  signal,
  detail
