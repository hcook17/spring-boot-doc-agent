import Common

/** Expected row from the JakartaMigration sanity checks. */
predicate sanityRow(string c1, string c2, string c3) {
  // A relocated javax return type should still be flagged as pending.
  exists(Method m |
    m.getDeclaringType().hasQualifiedName("com.example", "BookRepository") and
    m.getName() = "getEntityManager" and
    c1 = sym(m) and
    c2 = typeFqn(m.getReturnType()) and
    c3 = "pending"
  )
  or
  // A JSR-305 annotation must be excluded from the burndown.
  exists(string fqn |
    fqn = "javax.annotation.Nullable" and
    jsr305Symbol(fqn) and
    c1 = fqn and
    c2 = fqn and
    c3 = "jsr305-excluded"
  )
}

from string c1, string c2, string c3
where sanityRow(c1, c2, c3)
select c1, c2, c3
