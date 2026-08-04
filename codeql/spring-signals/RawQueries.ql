/**
 * @name Spring Data Queries
 * @description Detects @Query annotations and classifies them as JPQL or native.
 * @kind table
 * @id spring-signals/raw-queries
 */

import java
import SpringSignals

string queryTextFromAnnotation(Annotation ann) {
  result =
    concat(StringLiteral lit, int line, int col |
      lit = ann.getValue("value").getAChildExpr*() and
      line = lit.getLocation().getStartLine() and
      col = lit.getLocation().getStartColumn()
    |
      lit.getValue(), " " order by line, col
    )
  or
  (
    not exists(StringLiteral lit | lit = ann.getValue("value").getAChildExpr*()) and
    annotationStringValue(ann, "value", result)
  )
}

from Method m, Annotation ann, string query_text, string query_kind
where
  m.getAnAnnotation() = ann and
  isJavaSource(m) and
  ann.getType().(RefType).hasQualifiedName("org.springframework.data.jpa.repository", "Query") and
  query_text = queryTextFromAnnotation(ann) and
  (
    query_kind = "native" and annotationBooleanTrue(ann, "nativeQuery")
    or
    query_kind = "jpql" and not annotationBooleanTrue(ann, "nativeQuery")
  )
select
  m.getFile().getRelativePath() as file,
  ann.getLocation().getStartLine() as line,
  "raw_queries__query" as rule_id,
  query_text,
  query_kind
