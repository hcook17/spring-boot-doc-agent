import Common

from Annotation a, string extra
where
  (
    isOrMeta(a, "org.springframework.stereotype", "Controller")
    or
    isExactly(a, "org.springframework.web.bind.annotation", "RequestMapping")
    or
    isExactly(a, "org.springframework.web.bind.annotation", "GetMapping")
    or
    isExactly(a, "org.springframework.web.bind.annotation", "PostMapping")
    or
    isExactly(a, "org.springframework.web.bind.annotation", "PutMapping")
    or
    isExactly(a, "org.springframework.web.bind.annotation", "DeleteMapping")
    or
    isExactly(a, "org.springframework.web.bind.annotation", "PatchMapping")
    or
    isExactly(a, "org.springframework.web.bind.annotation", "PathVariable")
    or
    isExactly(a, "org.springframework.web.bind.annotation", "RequestParam")
    or
    isExactly(a, "org.springframework.web.bind.annotation", "RequestBody")
  ) and
  (
    a.getType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestBody") and
    extra = "body_binding"
    or
    not a.getType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestBody") and
    extra = attr(a, "value")
  )
select annotationFqn(a), sym(a), extra

