import Common

from Annotation a, string kind
where
  isExactly(a, "org.springframework.web.bind.annotation", "RequestBody") and
  signature("spring", "org.springframework.web.bind.annotation", "RequestBody", kind, _)
select annotationFqn(a), sym(a), kind
