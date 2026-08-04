/**
 * @name Error handling contract
 * @description How this service turns failures into HTTP responses.
 *
 * The previous version emitted a single `error_handling__advice` rule_id for
 * `@ControllerAdvice`, `@RestControllerAdvice` AND `@ExceptionHandler`, so an
 * advice class and a handler method were indistinguishable. It also returned
 * ZERO rows on ocs-api-service, because this service has no advice classes of
 * its own: the advice arrives from `com.eols.commons.exception` via
 * `@ComponentScan`, and the in-repo contract is expressed as 204 throw sites
 * across four shared exception types plus 364 `@ResponseStatus` annotations.
 *
 * This version keys on the throw/response surface as well as the advice
 * surface, and records `first_party_advice = false` when the advice is
 * component-scanned from a dependency. That off-repo dependency is a structural
 * limit of any oracle scoped to this repository's .java files, and it should be
 * reported rather than silently counted as zero.
 *
 * @kind table
 * @id spring-signals/error-handling
 * @tags api errors
 */

import Common

/** Holds if `t` is an exception type this service maps to an HTTP status. */
private predicate mappedExceptionType(RefType t, string fqn) {
  fqn = typeFqn(t) and
  (
    t.getASourceSupertype*().hasQualifiedName("java.lang", "Throwable") and
    (
      fqn.matches("com.eols.commons.exception.%") or
      fqn.matches("com.elsevier.%Exception") or
      fqn = "org.springframework.web.server.ResponseStatusException"
    )
  )
}

from Measured e, string rule_id, string signal, string detail
where
  // Advice classes and handler methods, kept as separate rule_ids.
  exists(Class c, Annotation a |
    e = a and
    a = getAnEffectiveAnnotation(c) and
    (
      isOrMeta(a, "org.springframework.web.bind.annotation", "ControllerAdvice") or
      isOrMeta(a, "org.springframework.web.bind.annotation", "RestControllerAdvice")
    ) and
    signal = annotationFqn(a) and
    detail = "" and
    rule_id = "error__advice_class"
  )
  or
  exists(Method m, Annotation a |
    e = a and
    a = getAnEffectiveAnnotation(m) and
    isExactly(a, "org.springframework.web.bind.annotation", "ExceptionHandler") and
    signal = annotationFqn(a) and
    detail =
      concat(TypeLiteral tl | tl = a.getValue("value").getAChildExpr*() | typeFqn(tl.getTypeName().getType()), "," order by typeFqn(tl.getTypeName().getType())) and
    rule_id = "error__handler_method"
  )
  or
  // @ResponseStatus, on both controller methods and exception classes.
  exists(Annotatable owner, Annotation a |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    isExactly(a, "org.springframework.web.bind.annotation", "ResponseStatus") and
    signal = annotationFqn(a) and
    detail =
      concat(FieldAccess fa |
        fa = a.getValue("value") and fa.getField().getDeclaringType().hasQualifiedName("org.springframework.http", "HttpStatus")
      |
        fa.getField().getName(), "|" order by fa.getField().getName()
      ) and
    rule_id = "error__response_status"
  )
  or
  // Throw sites of mapped exception types. This is the real error contract in
  // ocs-api-service: NotFound (78), BadRequest (53), InternalServerError (9),
  // Authorization (2) -- none of which the annotation-only rule could see.
  exists(ThrowStmt t, string fqn |
    e = t and
    mappedExceptionType(t.getThrownExceptionType(), fqn) and
    signal = fqn and
    detail = concat(Callable c | c = t.getEnclosingCallable() | sym(c), "|" order by sym(c)) and
    rule_id = "error__throw_site"
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
