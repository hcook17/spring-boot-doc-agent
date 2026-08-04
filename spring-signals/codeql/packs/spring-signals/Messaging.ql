/**
 * @name Messaging listeners and templates
 * @description Kafka/AMQP/JMS/SQS/Pulsar listeners and client types.
 *
 * P0 fix: `isMessagingTemplateType` previously compared a DECLARED type against
 * `hasQualifiedName`. For `KafkaTemplate<K,V>` the declared type is a
 * ParameterizedType whose name carries type arguments, so the predicate never
 * held -- the rule was dead code. Matching now goes through
 * `getSourceDeclaration()` plus a transitive supertype walk, which also picks up
 * interface-typed injection (`KafkaOperations`, `AmqpTemplate`, `JmsOperations`)
 * and project-local subclasses.
 *
 * STATUS ON ocs-api-service: zero rows. No messaging library is on the
 * classpath. This query is retained rather than deleted so that "no messaging"
 * is an asserted result rather than an untested one; see the coverage assertion
 * in harness/expected-empty.txt.
 *
 * @kind table
 * @id spring-signals/messaging
 * @tags messaging
 */

import Common

/** Holds if `t` is a messaging client type. Interfaces first, impls second. */
private predicate messagingClientType(Type t, string fqn) {
  typeIsOrExtends(t, "org.springframework.kafka.core", "KafkaOperations") and
  not typeIsOrExtends(t, "org.springframework.kafka.core", "KafkaTemplate") and
  fqn = "org.springframework.kafka.core.KafkaOperations"
  or
  typeIsOrExtends(t, "org.springframework.kafka.core", "KafkaTemplate") and
  fqn = "org.springframework.kafka.core.KafkaTemplate"
  or
  typeIsOrExtends(t, "org.springframework.amqp.core", "AmqpTemplate") and
  not typeIsOrExtends(t, "org.springframework.amqp.rabbit.core", "RabbitTemplate") and
  fqn = "org.springframework.amqp.core.AmqpTemplate"
  or
  typeIsOrExtends(t, "org.springframework.amqp.rabbit.core", "RabbitTemplate") and
  fqn = "org.springframework.amqp.rabbit.core.RabbitTemplate"
  or
  typeIsOrExtends(t, "org.springframework.jms.core", "JmsOperations") and
  fqn = "org.springframework.jms.core.JmsOperations"
  or
  typeIsOrExtends(t, "io.awspring.cloud.sqs.operations", "SqsTemplate") and
  fqn = "io.awspring.cloud.sqs.operations.SqsTemplate"
  or
  typeIsOrExtends(t, "org.springframework.pulsar.core", "PulsarTemplate") and
  fqn = "org.springframework.pulsar.core.PulsarTemplate"
  or
  typeIsOrExtends(t, "org.springframework.cloud.stream.function", "StreamBridge") and
  fqn = "org.springframework.cloud.stream.function.StreamBridge"
  or
  typeIsOrExtends(t, "org.springframework.messaging.simp", "SimpMessagingTemplate") and
  fqn = "org.springframework.messaging.simp.SimpMessagingTemplate"
}

/** Holds if `pkg`.`name` is a messaging listener annotation. */
private predicate listenerAnnotation(string pkg, string name) {
  pkg = "org.springframework.kafka.annotation" and
  name in ["KafkaListener", "KafkaHandler", "RetryableTopic", "DltHandler"]
  or
  pkg = "org.springframework.amqp.rabbit.annotation" and name = "RabbitListener"
  or
  pkg = "org.springframework.jms.annotation" and name = "JmsListener"
  or
  pkg = "io.awspring.cloud.sqs.annotation" and name = "SqsListener"
  or
  pkg = "org.springframework.pulsar.annotation" and name = "PulsarListener"
  or
  pkg = "org.springframework.integration.annotation" and
  name in ["ServiceActivator", "InboundChannelAdapter"]
}

from Measured e, string rule_id, string signal, string detail
where
  exists(Annotatable owner, Annotation a, string pkg, string name |
    e = a and
    a = getAnEffectiveAnnotation(owner) and
    isExactly(a, pkg, name) and
    listenerAnnotation(pkg, name) and
    signal = pkg + "." + name and
    detail = concat(string s | s = attr(a, "topics") and s != "" or s = attr(a, "queues") and s != "" or s = attr(a, "destination") and s != "" or s = attr(a, "value") and s != "" | s, "|" order by s) and
    rule_id = "messaging__listener"
  )
  or
  exists(Variable v, string fqn |
    e = v and
    messagingClientType(v.getType(), fqn) and
    signal = fqn and
    detail = v.getName() and
    rule_id = "messaging__client_type"
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
