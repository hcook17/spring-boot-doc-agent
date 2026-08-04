/**
 * @name Spring Error Handling
 * @description Detects controller advice types and exception handler methods.
 * @kind table
 * @id spring-signals/error-handling
 */

import java
import SpringSignals

from Annotatable decl, Annotation ann, string rule_id
where
  decl.getAnAnnotation() = ann and
  isJavaSource(ann) and
  (
    ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "ControllerAdvice") and
    rule_id = "error_handling__advice"
    or
    ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "RestControllerAdvice") and
    rule_id = "error_handling__rest_advice"
    or
    ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "ExceptionHandler") and
    rule_id = "error_handling__exception_handler"
  )
select
  decl.getFile().getRelativePath() as file,
  ann.getLocation().getStartLine() as line,
  rule_id
