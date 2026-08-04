import Common

from Annotation a
where
  isOrMeta(a, "org.springframework.boot.context.properties", "ConfigurationProperties")
  or
  isExactly(a, "org.springframework.beans.factory.annotation", "Value")
  or
  isExactly(a, "org.springframework.context.annotation", "Configuration")
  or
  isExactly(a, "org.springframework.context.annotation", "PropertySource")
  or
  isExactly(a, "org.springframework.context.annotation", "ComponentScan")
select annotationFqn(a), sym(a), attr(a, "value"), attr(a, "prefix")
