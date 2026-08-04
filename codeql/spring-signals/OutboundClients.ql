/**
 * @name Spring Outbound Clients
 * @description Detects Feign clients and outbound HTTP client usage.
 * @kind table
 * @id spring-signals/outbound-clients
 */

import java
import SpringSignals

predicate isOutboundClientType(RefType t) {
  erasureOrSourceSupertypeHasName(t, "org.springframework.web.client", "RestTemplate") or
  erasureOrSourceSupertypeHasName(t, "org.springframework.web.reactive.function.client", "WebClient") or
  erasureOrSourceSupertypeHasName(t, "org.springframework.web.client", "RestClient") or
  erasureOrSourceSupertypeHasName(t, "org.springframework.data.redis.core", "RedisTemplate") or
  erasureOrSourceSupertypeHasName(t, "org.springframework.data.redis.core", "ReactiveRedisTemplate") or
  erasureOrSourceSupertypeHasName(t, "org.springframework.data.redis.core", "StringRedisTemplate")
}

bindingset[pkg]
predicate isOutboundClientImportPackage(string pkg) {
  pkg.regexpMatch("org\\.springframework\\.web\\.client.*") or
  pkg.regexpMatch("org\\.springframework\\.web\\.reactive\\.function\\.client.*") or
  pkg.regexpMatch("org\\.springframework\\.data\\.redis\\.core.*")
}

predicate isFeignAnnotation(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("org.springframework.cloud.openfeign", "FeignClient")
}

from Element e, string rule_id
where
  (
    exists(Annotation ann |
      ann = e.(Annotatable).getAnAnnotation() and
      isJavaSource(ann) and
      isFeignAnnotation(ann) and
      rule_id = "outbound_clients__feign"
    )
  )
  or
  (
    exists(ImportType imp |
      imp = e and
      isJavaSource(imp) and
      isOutboundClientImportPackage(imp.getImportedType().getPackage().getName()) and
      rule_id = "outbound_clients__import"
    )
  )
  or
  (
    exists(ImportOnDemandFromPackage imp |
      imp = e and
      isJavaSource(imp) and
      isOutboundClientImportPackage(imp.getPackageHoldingImport().getName()) and
      rule_id = "outbound_clients__import"
    )
  )
  or
  (
    exists(ImportOnDemandFromType imp |
      imp = e and
      isJavaSource(imp) and
      isOutboundClientImportPackage(imp.getTypeHoldingImport().getPackage().getName()) and
      rule_id = "outbound_clients__import"
    )
  )
  or
  (
    exists(ImportStaticOnDemand imp |
      imp = e and
      isJavaSource(imp) and
      isOutboundClientImportPackage(imp.getTypeHoldingImport().getPackage().getName()) and
      rule_id = "outbound_clients__import"
    )
  )
  or
  (
    exists(ImportStaticTypeMember imp |
      imp = e and
      isJavaSource(imp) and
      isOutboundClientImportPackage(imp.getTypeHoldingImport().getPackage().getName()) and
      rule_id = "outbound_clients__import"
    )
  )
  or
  (
    exists(Variable v |
      v = e and
      isJavaSource(v) and
      isOutboundClientType(v.getType()) and
      rule_id = "outbound_clients__type_usage"
    )
  )
select
  e.getFile().getRelativePath() as file,
  e.getLocation().getStartLine() as line,
  rule_id
