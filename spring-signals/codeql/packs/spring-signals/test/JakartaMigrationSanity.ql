import Common

from Method m
where
  m.getDeclaringType().hasQualifiedName("com.example", "BookRepository") and
  m.getName() = "getEntityManager"
select sym(m), typeFqn(m.getReturnType())
