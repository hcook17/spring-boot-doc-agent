/*
 * WAVE 2 -- CARRIED OVER UNMODIFIED. Do not consume downstream yet.
 *
 * This query still emits the legacy 3-column schema (file, line, rule_id)
 * and still uses direct FQN matching without meta-annotation resolution.
 * The harness deliberately excludes it; see docs/CAMPAIGN.md wave 2.
 *
 * Known gap on ocs-api-service: matches 16 @SpringBootTest out of 176
 * test files. The suite is JUnit 4 (174 files, 133 @RunWith(
 * MockitoJUnitRunner)) on junit-vintage-engine, and the org\.junit.*
 * package regex conflates vintage with Jupiter -- which is exactly the
 * distinction the migration needs.
 */

/**
 * @name Spring Testing
 * @description Detects Spring Boot test annotations and test imports.
 * @kind table
 * @id spring-signals/testing
 */

import java

bindingset[e]
predicate isJavaSource(Element e) {
  e.getFile().getRelativePath().regexpMatch(".*\\.java$")
}

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
