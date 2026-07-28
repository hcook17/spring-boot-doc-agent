/**
 * @name Spring Error Handling
 * @description Detects controller advice and exception handler annotations.
 * @kind table
 * @id spring-signals/error-handling
 */

import java

bindingset[e]
predicate isJavaSource(Element e) {
  e.getFile().getRelativePath().regexpMatch(".*\\.java$")
}

from Annotatable decl, Annotation ann, string rule_id
where
  decl.getAnAnnotation() = ann and
  isJavaSource(ann) and
  (
    ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "ControllerAdvice") and
    rule_id = "error_handling__advice"
    or
    ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "RestControllerAdvice") and
    rule_id = "error_handling__advice"
    or
    ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "ExceptionHandler") and
    rule_id = "error_handling__advice"
  )
select
  decl.getFile().getRelativePath() as file,
  ann.getLocation().getStartLine() as line,
  rule_id
