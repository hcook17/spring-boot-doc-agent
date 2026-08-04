/**
 * @name Spring Configuration
 * @description Detects @ConfigurationProperties and @Value separately.
 * @kind table
 * @id spring-signals/configuration
 */

import java
import SpringSignals

from Annotatable decl, Annotation ann, string rule_id
where
  decl.getAnAnnotation() = ann and
  isJavaSource(ann) and
  (
    ann.getType().(RefType).hasQualifiedName("org.springframework.boot.context.properties", "ConfigurationProperties") and
    rule_id = "configuration__properties"
    or
    ann.getType().(RefType).hasQualifiedName("org.springframework.beans.factory.annotation", "Value") and
    rule_id = "configuration__value"
  )
select
  decl.getFile().getRelativePath() as file,
  ann.getLocation().getStartLine() as line,
  rule_id
