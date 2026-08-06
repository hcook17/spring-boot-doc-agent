/**
 * @name Configuration binding
 * @description `@ConfigurationProperties`, `@Value`, and configuration-class
 *              annotations.
 *
 * Fixes: the previous version emitted `configuration__properties` for BOTH
 * `@ConfigurationProperties` and `@Value`, making typed binding and ad-hoc SpEL
 * injection indistinguishable downstream. It also extracted no key, which is
 * the entire payload for config-drift analysis. ocs-api-service has 29 `@Value`
 * and ZERO `@ConfigurationProperties`; the split makes that visible.
 *
 * @kind table
 * @id spring-signals/configuration
 * @tags configuration
 */

import _Common

/**
 * Gets the property key referenced by a `@Value` expression, stripped of
 * `${...}` and any `:default` suffix.
 */
private string valueKey(Annotation a) {
  result =
    concat(string raw |
      raw = constantString(a.getValue("value"))
    |
      raw.regexpReplaceAll("^\\$\\{", "").regexpReplaceAll("(:.*)?\\}$", ""), "|"
    )
}

from Measured e, string rule_id, string signal, string detail
where
  exists(Annotatable owner, Annotation a |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    isOrMeta(a, "org.springframework.boot.context.properties", "ConfigurationProperties") and
    signal = attr(a, "prefix") + attr(a, "value") and
    detail = annotationFqn(a) and
    rule_id = "configuration__typed_binding"
  )
  or
  exists(Annotatable owner, Annotation a |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    isExactly(a, "org.springframework.beans.factory.annotation", "Value") and
    signal = valueKey(a) and
    detail = attr(a, "value") and
    rule_id = "configuration__value_injection"
  )
  or
  exists(Annotatable owner, Annotation a, string pkg, string name |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    isExactly(a, pkg, name) and
    signature("spring", pkg, name, "config", _) and
    signal = pkg + "." + name and
    detail = attr(a, "value") + attr(a, "basePackages") and
    rule_id = "configuration__config_annotation"
  )
select
  e.getPath() as file,
  e.getStartLine() as start_line,
  e.getEndLine() as end_line,
  e.getSourceSet() as source_set,
  schemaVersion() as schema_version,
  rule_id,
  "spring" as framework,
  "" as generation,
  sym(e) as symbol,
  signal,
  detail
