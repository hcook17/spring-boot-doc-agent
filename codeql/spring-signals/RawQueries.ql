/**
 * @name Spring Data Queries
 * @description Detects @Query annotations and classifies them as JPQL or native.
 * @kind table
 * @id spring-signals/raw-queries
 */

import java

bindingset[e]
predicate isJavaSource(Element e) {
  e.getFile().getRelativePath().regexpMatch(".*\\.java$")
}

from Method m, Annotation ann, string query_text, string query_kind
where
  m.getAnAnnotation() = ann and
  isJavaSource(m) and
  ann.getType().(RefType).hasQualifiedName("org.springframework.data.jpa.repository", "Query") and
  query_text = concat(StringLiteral lit, int line |
    lit = ann.getValue("value").getAChildExpr*() and
    line = lit.getLocation().getStartLine()
  | lit.getValue(), " " order by line) and
  (
    query_kind = "native" and ann.getValue("nativeQuery").(BooleanLiteral).getBooleanValue() = true
    or
    query_kind = "jpql" and not ann.getValue("nativeQuery").(BooleanLiteral).getBooleanValue() = true
  )
select
  m.getFile().getRelativePath() as file,
  ann.getLocation().getStartLine() as line,
  "raw_queries__query" as rule_id,
  query_text,
  query_kind
