/**
 * @name Spring Observability
 * @description Detects Micrometer/OpenTelemetry usage.
 * @kind table
 * @id spring-signals/observability
 */

import java
import SpringSignals

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
