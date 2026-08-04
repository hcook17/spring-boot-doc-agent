/**
 * @name Spring API Surface
 * @description Detects Spring controllers and HTTP mapping annotations.
 * @kind table
 * @id spring-signals/api-surface
 */

import java
import SpringSignals

predicate isControllerAnnotation(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "RestController") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.stereotype", "Controller")
}

predicate isMappingAnnotation(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "RequestMapping") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "GetMapping") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "PostMapping") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "PutMapping") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "PatchMapping") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "DeleteMapping")
}

string mappingHttpMethod(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "GetMapping") and
  result = "GET"
  or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "PostMapping") and
  result = "POST"
  or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "PutMapping") and
  result = "PUT"
  or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "PatchMapping") and
  result = "PATCH"
  or
  ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "DeleteMapping") and
  result = "DELETE"
  or
  (
    ann.getType().(RefType).hasQualifiedName("org.springframework.web.bind.annotation", "RequestMapping") and
    (
      annotationStringValue(ann, "method", result)
      or
      (
        not exists(string ignored | annotationStringValue(ann, "method", ignored)) and
        result = ""
      )
    )
  )
}

string mappingPath(Annotation ann) {
  annotationStringValue(ann, "value", result)
  or
  (
    not exists(string v | annotationStringValue(ann, "value", v)) and
    annotationStringValue(ann, "path", result)
  )
  or
  (
    not exists(string v | annotationStringValue(ann, "value", v)) and
    not exists(string p | annotationStringValue(ann, "path", p)) and
    result = ""
  )
}

from Annotatable decl, Annotation ann, string rule_id, string path, string http_method
where
  decl.getAnAnnotation() = ann and
  isJavaSource(ann) and
  (
    (
      isControllerAnnotation(ann) and
      rule_id = "api_surface__controller" and
      path = "" and
      http_method = ""
    )
    or
    (
      isMappingAnnotation(ann) and
      path = mappingPath(ann) and
      http_method = mappingHttpMethod(ann) and
      (
        (decl instanceof Class or decl instanceof Interface) and
        rule_id = "api_surface__class_mapping"
        or
        decl instanceof Method and
        rule_id = "api_surface__method_mapping"
      )
    )
  )
select
  decl.getFile().getRelativePath() as file,
  ann.getLocation().getStartLine() as line,
  rule_id,
  path,
  http_method
