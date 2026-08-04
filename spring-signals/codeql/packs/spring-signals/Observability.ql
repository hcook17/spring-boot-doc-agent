/*
 * WAVE 2 -- CARRIED OVER UNMODIFIED. Do not consume downstream yet.
 *
 * This query still emits the legacy 3-column schema (file, line, rule_id)
 * and still uses direct FQN matching without meta-annotation resolution.
 * The harness deliberately excludes it; see docs/CAMPAIGN.md wave 2.
 *
 * Known result on ocs-api-service: ZERO rows. No Micrometer or
 * OpenTelemetry imports. The real observability surface here is 34 slf4j
 * logger declarations and 48 @LogAccess sites (a custom AOP annotation
 * from eols-commons-logging), none of which this query models.
 */

/**
 * @name Spring Observability
 * @description Detects Micrometer/OpenTelemetry usage.
 * @kind table
 * @id spring-signals/observability
 */

import java

bindingset[e]
predicate isJavaSource(Element e) {
  e.getFile().getRelativePath().regexpMatch(".*\\.java$")
}

bindingset[pkg]
predicate isObservabilityImportPackage(string pkg) {
  pkg.regexpMatch("io\\.micrometer.*") or
  pkg.regexpMatch("io\\.opentelemetry.*")
}

from Element e, string rule_id
where
  (
    exists(Annotation ann |
      ann = e.(Annotatable).getAnAnnotation() and
      isJavaSource(ann) and
      ann.getType().(RefType).hasQualifiedName("io.micrometer.core.annotation", "Timed") and
      rule_id = "observability__timed"
    )
  )
  or
  (
    exists(Variable v |
      v = e and
      isJavaSource(v) and
      v.getType().(RefType).hasQualifiedName("io.micrometer.core.instrument", "MeterRegistry") and
      rule_id = "observability__meterregistry_type"
    )
  )
  or
  (
    exists(ImportType imp |
      imp = e and
      isJavaSource(imp) and
      isObservabilityImportPackage(imp.getImportedType().getPackage().getName()) and
      rule_id = "observability__import"
    )
  )
  or
  (
    exists(ImportOnDemandFromPackage imp |
      imp = e and
      isJavaSource(imp) and
      isObservabilityImportPackage(imp.getPackageHoldingImport().getName()) and
      rule_id = "observability__import"
    )
  )
  or
  (
    exists(ImportOnDemandFromType imp |
      imp = e and
      isJavaSource(imp) and
      isObservabilityImportPackage(imp.getTypeHoldingImport().getPackage().getName()) and
      rule_id = "observability__import"
    )
  )
  or
  (
    exists(ImportStaticOnDemand imp |
      imp = e and
      isJavaSource(imp) and
      isObservabilityImportPackage(imp.getTypeHoldingImport().getPackage().getName()) and
      rule_id = "observability__import"
    )
  )
  or
  (
    exists(ImportStaticTypeMember imp |
      imp = e and
      isJavaSource(imp) and
      isObservabilityImportPackage(imp.getTypeHoldingImport().getPackage().getName()) and
      rule_id = "observability__import"
    )
  )
select
  e.getFile().getRelativePath() as file,
  e.getLocation().getStartLine() as line,
  rule_id
