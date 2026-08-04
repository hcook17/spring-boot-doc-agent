/**
 * @name Spring Security
 * @description Detects Spring Security annotations and filter-chain types.
 * @kind table
 * @id spring-signals/security
 */

import java
import SpringSignals

from Element e, string rule_id
where
  (
    exists(Annotation ann |
      ann = e.(Annotatable).getAnAnnotation() and
      isJavaSource(ann) and
      (
        ann.getType().(RefType).hasQualifiedName("org.springframework.security.access.prepost", "PreAuthorize") or
        ann.getType().(RefType).hasQualifiedName("org.springframework.security.access.prepost", "PostAuthorize") or
        ann.getType().(RefType).hasQualifiedName("org.springframework.security.annotation", "Secured") or
        ann.getType().(RefType).hasQualifiedName("org.springframework.security.access.annotation", "Secured") or
        ann.getType().(RefType).hasQualifiedName("javax.annotation.security", "RolesAllowed") or
        ann.getType().(RefType).hasQualifiedName("jakarta.annotation.security", "RolesAllowed")
      ) and
      rule_id = "security__method"
    )
  )
  or
  (
    exists(Annotation ann |
      ann = e.(Annotatable).getAnAnnotation() and
      isJavaSource(ann) and
      (
        ann.getType().(RefType).hasQualifiedName("org.springframework.security.config.annotation.web.configuration", "EnableWebSecurity") or
        ann.getType().(RefType).hasQualifiedName("org.springframework.security.config.annotation.method.configuration", "EnableMethodSecurity")
      ) and
      rule_id = "security__config"
    )
  )
  or
  (
    exists(Method m |
      m = e and
      isJavaSource(m) and
      m.getReturnType().(RefType).hasQualifiedName("org.springframework.security.web", "SecurityFilterChain") and
      rule_id = "security__filterchain_type"
    )
  )
  or
  (
    exists(Variable v |
      v = e and
      isJavaSource(v) and
      v.getType().(RefType).hasQualifiedName("org.springframework.security.web", "SecurityFilterChain") and
      rule_id = "security__filterchain_type"
    )
  )
select
  e.getFile().getRelativePath() as file,
  e.getLocation().getStartLine() as line,
  rule_id
