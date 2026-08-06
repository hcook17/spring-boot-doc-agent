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
  // The rest of the relocated boundary (jakartaee-platform mappings.adoc):
  // these four were absent from the list once, silently never flagged.
  c1 = "javax.ejb" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  c1 = "javax.decorator" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  c1 = "javax.jws" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  c1 = "javax.jsp" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  // javax.security.auth is a split namespace: JAAS core is JDK-retained, the
  // JASPIC and JACC subtrees relocated. All three rows are pinned.
  c1 = "javax.security.auth" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  c1 = "javax.security.auth.message" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  c1 = "javax.security.jacc" and c2 = "namespace" and c3 = relocationStatus(c1)
  or
  c1 = "javax.crypto" and c2 = "namespace" and c3 = relocationStatus(c1)
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
  // The three jsr305-3.0.2 top-level symbols an earlier list missed; each was
  // a false pending-migration flag until listed.
  jsr305Symbol("javax.annotation.WillCloseWhenClosed") and
  c1 = "javax.annotation.WillCloseWhenClosed" and c2 = "jsr305" and c3 = "excluded"
  or
  jsr305Symbol("javax.annotation.CheckForSigned") and
  c1 = "javax.annotation.CheckForSigned" and c2 = "jsr305" and c3 = "excluded"
  or
  jsr305Symbol("javax.annotation.Detainted") and
  c1 = "javax.annotation.Detainted" and c2 = "jsr305" and c3 = "excluded"
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
