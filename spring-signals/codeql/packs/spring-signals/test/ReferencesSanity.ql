import java

from Element e
where
  exists(Import imp |
    imp = e and
    imp.getFile().getRelativePath().regexpMatch(".*\\.java$")
  )
  or
  exists(CompilationUnit cu |
    cu = e and
    cu.getFile().getRelativePath().regexpMatch(".*\\.java$") and
    cu.getPackage().getName() != ""
  )
  or
  exists(Annotation ann |
    ann = e.(Annotatable).getAnAnnotation() and
    ann.getFile().getRelativePath().regexpMatch(".*\\.java$") and
    (
      ann.getType().(RefType).hasQualifiedName("org.springframework.stereotype", "Service") or
      ann.getType().(RefType).hasQualifiedName("org.springframework.stereotype", "Component") or
      ann.getType().(RefType).hasQualifiedName("org.springframework.stereotype", "Repository") or
      ann.getType().(RefType).hasQualifiedName("org.springframework.context.annotation", "Configuration")
    )
  )
select e.getFile().getRelativePath(), e.getLocation().getStartLine(), e.getLocation().getEndLine()
