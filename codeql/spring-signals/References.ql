/**
 * @name Spring References
 * @description Builds a repo-wide index of imports, packages, and bean stereotypes.
 * @kind table
 * @id spring-signals/references
 */

import java
import SpringSignals

predicate isStereotype(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("org.springframework.stereotype", "Service") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.stereotype", "Component") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.stereotype", "Repository") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.context.annotation", "Configuration")
}

from Element e, string rule_id, string file_path, int start_line
where
  (
    exists(Import imp |
      imp = e and
      isJavaSource(imp) and
      rule_id = "references__import" and
      file_path = imp.getFile().getRelativePath() and
      start_line = imp.getLocation().getStartLine()
    )
  )
  or
  (
    exists(CompilationUnit cu |
      cu = e and
      isJavaSource(cu) and
      cu.getPackage().getName() != "" and
      rule_id = "references__package" and
      file_path = cu.getFile().getRelativePath() and
      start_line = cu.getLocation().getStartLine()
    )
  )
  or
  (
    exists(Annotation ann |
      ann = e.(Annotatable).getAnAnnotation() and
      isJavaSource(ann) and
      isStereotype(ann) and
      rule_id = "references__stereotype" and
      file_path = e.getFile().getRelativePath() and
      start_line = ann.getLocation().getStartLine()
    )
  )
select
  file_path as file,
  start_line as line,
  rule_id
