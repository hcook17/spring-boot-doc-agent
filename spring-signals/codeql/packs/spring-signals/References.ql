/*
 * WAVE 2 -- CARRIED OVER UNMODIFIED. Do not consume downstream yet.
 *
 * This query still emits the legacy 3-column schema (file, line, rule_id)
 * and still uses direct FQN matching without meta-annotation resolution.
 * The harness deliberately excludes it; see docs/CAMPAIGN.md wave 2.
 *
 * Known gap on ocs-api-service: isStereotype matches 64 sites but misses
 * all 48 @RestController (meta @Controller -> @Component), the
 * @SpringBootApplication on Application, and the ~44 Spring Data
 * repositories that are beans with no stereotype annotation at all.
 */

/**
 * @name Spring References
 * @description Builds a repo-wide index of imports, packages, and bean stereotypes.
 * @kind table
 * @id spring-signals/references
 */

import java

bindingset[e]
predicate isJavaSource(Element e) {
  e.getFile().getRelativePath().regexpMatch(".*\\.java$")
}

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
