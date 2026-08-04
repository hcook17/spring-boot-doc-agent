import java

from Element e
where
  exists(Annotation ann |
    ann = e.(Annotatable).getAnAnnotation() and
    ann.getType().(RefType).hasQualifiedName("org.springframework.boot.test.context", "SpringBootTest")
  )
  or
  exists(ImportType imp |
    imp = e and
    imp.getImportedType().getPackage().getName().regexpMatch("org\\.junit.*")
  )
select e.getFile().getRelativePath(), e.getLocation().getStartLine(), e.getLocation().getEndLine()
