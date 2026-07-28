/**
 * @name Spring Messaging
 * @description Detects messaging listeners and templates.
 * @kind table
 * @id spring-signals/messaging
 */

import java

bindingset[e]
predicate isJavaSource(Element e) {
  e.getFile().getRelativePath().regexpMatch(".*\\.java$")
}

predicate isMessagingTemplateType(RefType t) {
  t.hasQualifiedName("org.springframework.kafka.core", "KafkaTemplate") or
  t.hasQualifiedName("org.springframework.amqp.rabbit.core", "RabbitTemplate") or
  t.hasQualifiedName("org.springframework.jms.core", "JmsTemplate") or
  t.hasQualifiedName("io.awspring.cloud.sqs.operations", "SqsTemplate")
}

bindingset[pkg]
predicate isMessagingTemplateImportPackage(string pkg) {
  pkg.regexpMatch("org\\.springframework\\.kafka\\.core.*") or
  pkg.regexpMatch("org\\.springframework\\.amqp\\.rabbit\\.core.*") or
  pkg.regexpMatch("org\\.springframework\\.jms\\.core.*") or
  pkg.regexpMatch("io\\.awspring\\.cloud\\.sqs.*")
}

predicate isMessagingListenerAnnotation(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("org.springframework.kafka.annotation", "KafkaListener") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.amqp.rabbit.annotation", "RabbitListener") or
  ann.getType().(RefType).hasQualifiedName("org.springframework.jms.annotation", "JmsListener") or
  ann.getType().(RefType).hasQualifiedName("io.awspring.cloud.sqs.annotation", "SqsListener")
}

from Element e, string rule_id
where
  (
    exists(Annotation ann |
      ann = e.(Annotatable).getAnAnnotation() and
      isJavaSource(ann) and
      isMessagingListenerAnnotation(ann) and
      rule_id = "messaging__listener"
    )
  )
  or
  (
    exists(ImportType imp |
      imp = e and
      isJavaSource(imp) and
      isMessagingTemplateImportPackage(imp.getImportedType().getPackage().getName()) and
      rule_id = "messaging__import"
    )
  )
  or
  (
    exists(ImportOnDemandFromPackage imp |
      imp = e and
      isJavaSource(imp) and
      isMessagingTemplateImportPackage(imp.getPackageHoldingImport().getName()) and
      rule_id = "messaging__import"
    )
  )
  or
  (
    exists(ImportOnDemandFromType imp |
      imp = e and
      isJavaSource(imp) and
      isMessagingTemplateImportPackage(imp.getTypeHoldingImport().getPackage().getName()) and
      rule_id = "messaging__import"
    )
  )
  or
  (
    exists(ImportStaticOnDemand imp |
      imp = e and
      isJavaSource(imp) and
      isMessagingTemplateImportPackage(imp.getTypeHoldingImport().getPackage().getName()) and
      rule_id = "messaging__import"
    )
  )
  or
  (
    exists(ImportStaticTypeMember imp |
      imp = e and
      isJavaSource(imp) and
      isMessagingTemplateImportPackage(imp.getTypeHoldingImport().getPackage().getName()) and
      rule_id = "messaging__import"
    )
  )
  or
  (
    exists(Variable v |
      v = e and
      isJavaSource(v) and
      isMessagingTemplateType(v.getType()) and
      rule_id = "messaging__type_usage"
    )
  )
select
  e.getFile().getRelativePath() as file,
  e.getLocation().getStartLine() as line,
  rule_id
