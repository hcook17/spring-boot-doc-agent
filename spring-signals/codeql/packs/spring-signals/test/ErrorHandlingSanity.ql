import Common

from Annotation a
where
  isOrMeta(a, "org.springframework.web.bind.annotation", "ControllerAdvice")
  or
  isExactly(a, "org.springframework.web.bind.annotation", "ExceptionHandler")
  or
  isExactly(a, "org.springframework.web.bind.annotation", "ResponseStatus")
select annotationFqn(a), sym(a), a.getValue("value").(FieldAccess).getField().getName()
