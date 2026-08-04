import Common

from Annotation a
where
  isExactly(a, "org.springframework.cloud.openfeign", "FeignClient")
  or
  isExactly(a, "org.springframework.web.service.annotation", "HttpExchange")
  or
  isExactly(a, "org.springframework.web.service.annotation", "GetExchange")
  or
  isExactly(a, "org.springframework.web.service.annotation", "PostExchange")
select annotationFqn(a), sym(a), attr(a, "value"), attr(a, "url")
