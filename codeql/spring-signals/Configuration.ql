/**
 * @name Spring Configuration
 * @description Detects configuration property annotations and @Value.
 * @kind table
 * @id spring-signals/configuration
 */

import java

bindingset[e]
predicate isJavaSource(Element e) {
  e.getFile().getRelativePath().regexpMatch(".*\\.java$")
}

from Annotatable decl, Annotation ann, string rule_id
where
  decl.getAnAnnotation() = ann and
  isJavaSource(ann) and
  (
    ann.getType().(RefType).hasQualifiedName("org.springframework.boot.context.properties", "ConfigurationProperties") and
    rule_id = "configuration__properties"
    or
    ann.getType().(RefType).hasQualifiedName("org.springframework.beans.factory.annotation", "Value") and
    rule_id = "configuration__properties"
  )
select
  decl.getFile().getRelativePath() as file,
  ann.getLocation().getStartLine() as line,
  rule_id
