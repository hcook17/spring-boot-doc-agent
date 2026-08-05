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
  // A JSR-305 annotation must be excluded from the burndown. This row is
  // produced only if the exclusion is removed, so the test fails if
  // jsr305Symbol stops covering javax.annotation.Nullable.
  exists(Annotation a |
    a.getType().getSourceDeclaration().hasQualifiedName("javax.annotation", "Nullable") and
    exists(Annotatable owner | a = getAnEffectiveAnnotation(owner)) and
    not jsr305Symbol(annotationFqn(a)) and
    c1 = annotationFqn(a) and
    c2 = sym(a) and
    c3 = "jakarta_migration_would_flag"
  )
}

from string c1, string c2, string c3
where sanityRow(c1, c2, c3)
select c1, c2, c3
