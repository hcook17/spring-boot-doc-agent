import java

from Element e
where
  exists(Annotation ann |
    ann = e.(Annotatable).getAnAnnotation() and
    (
      ann.getType().(RefType).hasQualifiedName("org.springframework.security.access.prepost", "PreAuthorize") or
      ann.getType().(RefType).hasQualifiedName("org.springframework.security.config.annotation.web.configuration", "EnableWebSecurity")
    )
  )
  or
  exists(Method m |
    m = e and
    m.getReturnType().(RefType).hasQualifiedName("org.springframework.security.web", "SecurityFilterChain")
  )
select e.getFile().getRelativePath(), e.getLocation().getStartLine(), e.getLocation().getEndLine()
