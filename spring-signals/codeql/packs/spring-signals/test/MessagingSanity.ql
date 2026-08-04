import Common

from Annotation a
where
  isExactly(a, "org.springframework.kafka.annotation", "KafkaListener")
select annotationFqn(a), sym(a), attr(a, "topics")
