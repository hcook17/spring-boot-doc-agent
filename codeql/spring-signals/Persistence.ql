/**
 * @name Spring Persistence
 * @description Detects JPA entities, repositories, and mapping annotations.
 * @kind table
 * @id spring-signals/persistence
 */

import java
import SpringSignals

predicate isEntityAnnotation(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("jakarta.persistence", "Entity") or
  ann.getType().(RefType).hasQualifiedName("javax.persistence", "Entity")
}

predicate isTableAnnotation(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("jakarta.persistence", "Table") or
  ann.getType().(RefType).hasQualifiedName("javax.persistence", "Table")
}

predicate isRepositorySupertype(RefType t) {
  t.getErasure().(RefType).hasQualifiedName("org.springframework.data.jpa.repository", "JpaRepository") or
  t.getErasure().(RefType).hasQualifiedName("org.springframework.data.repository", "CrudRepository") or
  t.getErasure().(RefType).hasQualifiedName("org.springframework.data.repository", "PagingAndSortingRepository") or
  t.getErasure().(RefType).hasQualifiedName("org.springframework.data.mongodb.repository", "MongoRepository") or
  t.getErasure().(RefType).hasQualifiedName("org.springframework.data.repository.reactive", "ReactiveCrudRepository")
}

predicate isColumnAnnotation(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("jakarta.persistence", "Column") or
  ann.getType().(RefType).hasQualifiedName("javax.persistence", "Column")
}

predicate isJoinColumnAnnotation(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("jakarta.persistence", "JoinColumn") or
  ann.getType().(RefType).hasQualifiedName("javax.persistence", "JoinColumn") or
  ann.getType().(RefType).hasQualifiedName("jakarta.persistence", "JoinTable") or
  ann.getType().(RefType).hasQualifiedName("javax.persistence", "JoinTable")
}

predicate isRelationAnnotation(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("jakarta.persistence", "ManyToOne") or
  ann.getType().(RefType).hasQualifiedName("javax.persistence", "ManyToOne") or
  ann.getType().(RefType).hasQualifiedName("jakarta.persistence", "OneToMany") or
  ann.getType().(RefType).hasQualifiedName("javax.persistence", "OneToMany") or
  ann.getType().(RefType).hasQualifiedName("jakarta.persistence", "ManyToMany") or
  ann.getType().(RefType).hasQualifiedName("javax.persistence", "ManyToMany") or
  ann.getType().(RefType).hasQualifiedName("jakarta.persistence", "OneToOne") or
  ann.getType().(RefType).hasQualifiedName("javax.persistence", "OneToOne")
}

predicate isIdAnnotation(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("jakarta.persistence", "Id") or
  ann.getType().(RefType).hasQualifiedName("javax.persistence", "Id") or
  ann.getType().(RefType).hasQualifiedName("jakarta.persistence", "EmbeddedId") or
  ann.getType().(RefType).hasQualifiedName("javax.persistence", "EmbeddedId") or
  ann.getType().(RefType).hasQualifiedName("jakarta.persistence", "GeneratedValue") or
  ann.getType().(RefType).hasQualifiedName("javax.persistence", "GeneratedValue")
}

predicate isTransactionalAnnotation(Annotation ann) {
  ann.getType().(RefType).hasQualifiedName("org.springframework.transaction.annotation", "Transactional") or
  ann.getType().(RefType).hasQualifiedName("javax.transaction", "Transactional") or
  ann.getType().(RefType).hasQualifiedName("jakarta.transaction", "Transactional")
}

/**
 * Table name for an entity class. Total for every class: when `@Table` is
 * present without a compile-time `name`, result is "" (unnamed), not "no row".
 */
string getTableName(Class c) {
  exists(Annotation ann |
    ann = c.getAnAnnotation() and
    isTableAnnotation(ann) and
    annotationStringValue(ann, "name", result)
  )
  or
  (
    exists(Annotation ann | ann = c.getAnAnnotation() and isTableAnnotation(ann)) and
    not exists(Annotation ann, string ignored |
      ann = c.getAnAnnotation() and
      isTableAnnotation(ann) and
      annotationStringValue(ann, "name", ignored)
    ) and
    result = ""
  )
  or
  (
    not exists(Annotation ann | ann = c.getAnAnnotation() and isTableAnnotation(ann)) and
    result = ""
  )
}

/** Entity type argument from a parameterized Spring Data repository ancestor. */
string repositoryEntityName(Interface i) {
  result =
    min(string n |
      exists(ParameterizedType pt |
        pt = i.getASourceSupertype+() and
        isRepositorySupertype(pt) and
        n = pt.getTypeArgument(0).getName()
      )
    |
      n
    )
  or
  (
    not exists(ParameterizedType pt |
      pt = i.getASourceSupertype+() and isRepositorySupertype(pt)
    ) and
    result = ""
  )
}

from Element e, string rule_id, string class_name, string table_name, string repository_name, string entity_name
where
  (
    exists(Class c |
      c = e and
      isJavaSource(c) and
      isEntityAnnotation(c.getAnAnnotation()) and
      rule_id = "persistence__entity" and
      class_name = c.getName() and
      table_name = getTableName(c) and
      repository_name = "" and
      entity_name = ""
    )
  )
  or
  (
    exists(Interface i |
      i = e and
      isJavaSource(i) and
      exists(RefType ancestor |
        ancestor = i.getASourceSupertype+() and
        isRepositorySupertype(ancestor)
      ) and
      rule_id = "persistence__repository" and
      class_name = "" and
      table_name = "" and
      repository_name = i.getName() and
      entity_name = repositoryEntityName(i)
    )
  )
  or
  (
    exists(Annotation ann |
      ann = e and
      isJavaSource(ann) and
      isColumnAnnotation(ann) and
      rule_id = "persistence__column" and
      class_name = "" and
      table_name = "" and
      repository_name = "" and
      entity_name = ""
    )
  )
  or
  (
    exists(Annotation ann |
      ann = e and
      isJavaSource(ann) and
      isJoinColumnAnnotation(ann) and
      rule_id = "persistence__join_column" and
      class_name = "" and
      table_name = "" and
      repository_name = "" and
      entity_name = ""
    )
  )
  or
  (
    exists(Annotation ann |
      ann = e and
      isJavaSource(ann) and
      isRelationAnnotation(ann) and
      rule_id = "persistence__relation" and
      class_name = "" and
      table_name = "" and
      repository_name = "" and
      entity_name = ""
    )
  )
  or
  (
    exists(Annotation ann |
      ann = e and
      isJavaSource(ann) and
      isIdAnnotation(ann) and
      rule_id = "persistence__id" and
      class_name = "" and
      table_name = "" and
      repository_name = "" and
      entity_name = ""
    )
  )
  or
  (
    exists(Annotation ann |
      ann = e and
      isJavaSource(ann) and
      isTransactionalAnnotation(ann) and
      rule_id = "persistence__transactional" and
      class_name = "" and
      table_name = "" and
      repository_name = "" and
      entity_name = ""
    )
  )
select
  e.getFile().getRelativePath() as file,
  e.getLocation().getStartLine() as line,
  rule_id,
  class_name,
  table_name,
  repository_name,
  entity_name
