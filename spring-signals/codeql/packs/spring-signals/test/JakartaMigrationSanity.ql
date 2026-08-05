import Common
import Jakarta

/** Gets "relocated" or "retained" for a candidate javax namespace. */
bindingset[pkg]
private string relocationStatus(string pkg) {
  if relocatedJavaxNamespace(pkg) then result = "relocated" else result = "retained"
}

/** Expected row from the JakartaMigration sanity checks. */
predicate sanityRow(string c1, string c2, string c3) {
  // The split-namespace boundary, both directions. Every row is unconditional,
  // so a boundary edit flips a pinned value instead of dropping a row.
  c1 = "javax.annotation" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  c1 = "javax.annotation.security" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  c1 = "javax.annotation.sql" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  c1 = "javax.annotation.processing" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  c1 = "javax.annotation.concurrent" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  c1 = "javax.annotation.meta" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  c1 = "javax.sql" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  // JSR-250 symbols are pending migration work; JSR-305 symbols are not.
  not jsr305Symbol("javax.annotation.PostConstruct") and
  c1 = "javax.annotation.PostConstruct" and c2 = "jsr250" and c3 = "pending"
  or
  not jsr305Symbol("javax.annotation.Resource") and
  c1 = "javax.annotation.Resource" and c2 = "jsr250" and c3 = "pending"
  or
  jsr305Symbol("javax.annotation.Nullable") and
  c1 = "javax.annotation.Nullable" and c2 = "jsr305" and c3 = "excluded"
  or
  // A relocated javax return type should still be flagged as pending.
  exists(Method m |
    m.getDeclaringType().hasQualifiedName("com.example", "BookRepository") and
    m.getName() = "getEntityManager" and
    c1 = sym(m) and
    c2 = typeFqn(m.getReturnType()) and
    c3 = "pending"
  )
  or
  // A real @Nullable use must be recognised as JSR-305. This row disappears --
  // failing the test -- if jsr305Symbol stops covering javax.annotation.Nullable.
  exists(Annotation a |
    a.getType().getSourceDeclaration().hasQualifiedName("javax.annotation", "Nullable") and
    exists(Annotatable owner | a = getAnEffectiveAnnotation(owner)) and
    jsr305Symbol(annotationFqn(a)) and
    c1 = annotationFqn(a) and
    c2 = sym(a) and
    c3 = "jsr305_excluded"
  )
}

from string c1, string c2, string c3
where sanityRow(c1, c2, c3)
select c1, c2, c3
