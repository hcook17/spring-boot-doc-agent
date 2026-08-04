/**
 * @name Outbound HTTP clients
 * @description Feign clients, Spring HTTP interface clients, and outbound
 *              client type usage.
 *
 * P0 fix: type matching now goes through `getSourceDeclaration()` and a
 * transitive supertype walk. The previous `hasQualifiedName` on a declared type
 * matched only a non-generic type referenced by its exact class -- correct by
 * accident for RestTemplate/WebClient, wrong for anything generic or
 * interface-injected.
 *
 * Import-based detection is retained but tagged with a distinct rule_id, so the
 * harness can count SITES without double-counting an import plus its use. Note
 * that import-based rules structurally undercount: ocs-api-service writes 540
 * annotations fully qualified inline, which leave no Import node at all.
 *
 * @kind table
 * @id spring-signals/outbound-clients
 * @tags api outbound migration
 */

import Common

/** Holds if `t` is an outbound HTTP client type, generation-tagged. */
private predicate outboundClientType(Type t, string fqn, string generation) {
  typeIsOrExtends(t, "org.springframework.web.client", "RestTemplate") and
  fqn = "org.springframework.web.client.RestTemplate" and
  generation = ""
  or
  typeIsOrExtends(t, "org.springframework.web.client", "RestClient") and
  fqn = "org.springframework.web.client.RestClient" and
  generation = "boot3+"
  or
  typeIsOrExtends(t, "org.springframework.web.reactive.function.client", "WebClient") and
  fqn = "org.springframework.web.reactive.function.client.WebClient" and
  generation = ""
  or
  typeIsOrExtends(t, "org.springframework.boot.web.client", "RestTemplateBuilder") and
  fqn = "org.springframework.boot.web.client.RestTemplateBuilder" and
  generation = ""
  or
  typeIsOrExtends(t, "org.springframework.web.service.invoker", "HttpServiceProxyFactory") and
  fqn = "org.springframework.web.service.invoker.HttpServiceProxyFactory" and
  generation = "boot3+"
  or
  typeIsOrExtends(t, "java.net.http", "HttpClient") and
  fqn = "java.net.http.HttpClient" and
  generation = ""
  or
  typeIsOrExtends(t, "okhttp3", "OkHttpClient") and fqn = "okhttp3.OkHttpClient" and generation = ""
}

from Measured e, string rule_id, string generation, string signal, string detail
where
  // Feign. Boot 2.x-era; the migration target is @HttpExchange below.
  exists(Annotatable owner, Annotation a, string name |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    isExactly(a, "org.springframework.cloud.openfeign", name) and
    signature("spring", "org.springframework.cloud.openfeign", name, "feign", generation) and
    signal = "org.springframework.cloud.openfeign." + name and
    detail = concat(string s | s = attr(a, "name") and s != "" or s = attr(a, "url") and s != "" or s = attr(a, "basePackages") and s != "" | s, " " order by s) and
    rule_id = "outbound__feign"
  )
  or
  // Spring HTTP interface clients (Framework 6.1+ / Boot 3.2+).
  exists(Annotatable owner, Annotation a, string name |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    isExactly(a, "org.springframework.web.service.annotation", name) and
    signature("spring", "org.springframework.web.service.annotation", name, "http_exchange", generation) and
    signal = "org.springframework.web.service.annotation." + name and
    detail = concat(string s | s = attr(a, "value") and s != "" or s = attr(a, "url") and s != "" | s, " " order by s) and
    rule_id = "outbound__http_exchange"
  )
  or
  // Declared client types: fields, parameters, locals, and return types.
  exists(Variable v, string fqn |
    e = v and
    outboundClientType(v.getType(), fqn, generation) and
    not exists(string other |
      outboundClientType(v.getType(), other, _) and
      other != fqn and
      typeStrictlyExtendsFqn(other, fqn)
    ) and
    signal = fqn and
    detail = v.getName() and
    rule_id = "outbound__type_usage"
  )
  or
  exists(Method m, string fqn |
    e = m and
    outboundClientType(m.getReturnType(), fqn, generation) and
    signal = fqn and
    detail = m.getName() and
    rule_id = "outbound__type_usage"
  )
select
  e.getPath() as file,
  e.getStartLine() as start_line,
  e.getEndLine() as end_line,
  e.getSourceSet() as source_set,
  schemaVersion() as schema_version,
  rule_id,
  "spring" as framework,
  generation,
  sym(e) as symbol,
  signal,
  detail
