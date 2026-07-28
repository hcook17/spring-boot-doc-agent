/**
 * @name Spring API Surface
 * @description Detects Spring controllers and HTTP mapping annotations.
 * @kind table
 * @id spring-signals/api-surface
 */

import java

bindingset[e]
predicate isJavaSource(Element e) {
  e.getFile().getRelativePath().regexpMatch(".*\\.java$")
}

predicate isApiMappingAnnotation(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "RestController") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.stereotype", "Controller") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "RequestMapping") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "GetMapping") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "PostMapping") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "PutMapping") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "PatchMapping") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "DeleteMapping")
}

from Annotatable decl, Annotation ann, string rule_id
where
  decl.getAnAnnotation() = ann and
  isJavaSource(ann) and
  isApiMappingAnnotation(ann) and
  (
    if ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "RestController") or
       ann.getType().(RefType).hasQualifiedName("org.springframework.stereotype", "Controller")
    then rule_id = "api_surface__controller"
    else rule_id = "api_surface__mapping"
  )
select
  decl.getFile().getRelativePath() as file,
  ann.getLocation().getStartLine() as line,
  rule_id
