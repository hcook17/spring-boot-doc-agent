import Common

from Annotation a
where
  isOrMeta(a, "org.springframework.stereotype", "Controller")
  or
  isExactly(a, "org.springframework.web.bind.annotation", "RequestMapping")
  or
  isExactly(a, "org.springframework.web.bind.annotation", "GetMapping")
  or
  isExactly(a, "org.springframework.web.bind.annotation", "PathVariable")
  or
  isExactly(a, "org.springframework.web.bind.annotation", "RequestParam")
select annotationFqn(a), sym(a), attr(a, "value")
