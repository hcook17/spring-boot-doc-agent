import java

from Element e
where
  exists(Annotation ann |
    ann = e.(Annotatable).getAnAnnotation() and
    ann.getType().(RefType).hasQualifiedName("io.micrometer.core.annotation", "Timed")
  )
  or
  exists(Variable v |
    v = e and
    v.getType().(RefType).hasQualifiedName("io.micrometer.core.instrument", "MeterRegistry")
  )
  or
  exists(ImportType imp |
    imp = e and
    imp.getImportedType().getPackage().getName().regexpMatch("io\\.micrometer.*")
  )
select e.getFile().getRelativePath(), e.getLocation().getStartLine(), e.getLocation().getEndLine()
