import Common

from Annotation a
where
  isOrMeta(a, "org.springframework.data.jpa.repository", "Query")
select annotationFqn(a), sym(a), concatenatedText(a.getValue("value")), a.getValue("nativeQuery").(CompileTimeConstantExpr).getBooleanValue()
