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
select annotationFqn(a), sym(a), attr(a, "value"), attr(a, "url"),
  // The query's actual detail extraction for the feign arm. Pinning it makes
  // the test fail if `value` is dropped from the attribute list again.
  attrs(a, "value,name,url,basePackages")
