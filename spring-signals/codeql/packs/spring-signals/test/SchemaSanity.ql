import Common

from Annotation a
where a.getType().getSourceDeclaration().getPackage().getName() = "org.springframework.web.bind.annotation"
select annotationFqn(a), sym(a), attr(a, "value")
