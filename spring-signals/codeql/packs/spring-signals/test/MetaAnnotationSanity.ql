import Common

boolean isControllerMeta(Annotation a) {
  isOrMeta(a, "org.springframework.stereotype", "Controller") and result = true
  or
  not isOrMeta(a, "org.springframework.stereotype", "Controller") and result = false
}

from Annotation a
where
  a.getType().getSourceDeclaration().getPackage().getName() =
    "org.springframework.web.bind.annotation"
select annotationFqn(a), sym(a), isControllerMeta(a)
