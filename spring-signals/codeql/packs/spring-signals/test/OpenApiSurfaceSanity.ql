import Common

from Annotation a
where
  isExactly(a, "io.swagger.v3.oas.annotations", "Operation")
  or
  isExactly(a, "io.swagger.v3.oas.annotations.responses", "ApiResponse")
  or
  isExactly(a, "io.swagger.v3.oas.annotations.tags", "Tag")
  or
  isExactly(a, "io.swagger.annotations", "ApiOperation")
  or
  isExactly(a, "io.swagger.annotations", "Api")
select annotationFqn(a), sym(a), attr(a, "value"), attr(a, "summary"), attr(a, "description")
