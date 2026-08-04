/**
 * @name Spring Testing
 * @description Detects Spring Boot test annotations and test imports.
 * @kind table
 * @id spring-signals/testing
 */

import java
import SpringSignals

bindingset[pkg]
predicate isTestImportPackage(string pkg) {
  pkg.regexpMatch("org\\.testcontainers.*") or
  pkg.regexpMatch("org\\.springframework\\.boot\\.test.*") or
  pkg.regexpMatch("org\\.springframework\\.test.*") or
  pkg.regexpMatch("org\\.junit.*") or
  pkg.regexpMatch("org\\.mockito.*")
}

from Element e, string rule_id
where
  (
    exists(Annotation ann |
      ann = e.(Annotatable).getAnAnnotation() and
      isJavaSource(ann) and
      ann.getType().(RefType).hasQualifiedName("org.springframework.boot.test.context", "SpringBootTest") and
      rule_id = "testing__springboottest"
    )
  )
  or
  (
    exists(ImportType imp |
      imp = e and
      isJavaSource(imp) and
      isTestImportPackage(imp.getImportedType().getPackage().getName()) and
      rule_id = "testing__import"
    )
  )
  or
  (
    exists(ImportOnDemandFromPackage imp |
      imp = e and
      isJavaSource(imp) and
      isTestImportPackage(imp.getPackageHoldingImport().getName()) and
      rule_id = "testing__import"
    )
  )
  or
  (
    exists(ImportOnDemandFromType imp |
      imp = e and
      isJavaSource(imp) and
      isTestImportPackage(imp.getTypeHoldingImport().getPackage().getName()) and
      rule_id = "testing__import"
    )
  )
  or
  (
    exists(ImportStaticOnDemand imp |
      imp = e and
      isJavaSource(imp) and
      isTestImportPackage(imp.getTypeHoldingImport().getPackage().getName()) and
      rule_id = "testing__import"
    )
  )
  or
  (
    exists(ImportStaticTypeMember imp |
      imp = e and
      isJavaSource(imp) and
      isTestImportPackage(imp.getTypeHoldingImport().getPackage().getName()) and
      rule_id = "testing__import"
    )
  )
select
  e.getFile().getRelativePath() as file,
  e.getLocation().getStartLine() as line,
  rule_id
