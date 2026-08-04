/**
 * Framework signature catalog -- Spring / JPA / Hibernate / OpenAPI.
 *
 * WHY THIS LIVES IN THE QUERY PACK, NOT THE LIBRARY PACK.
 *
 * It used to sit in `java-signals-lib`, which is documented as framework-agnostic.
 * Moving the meta-edge table out was only half the fix: this file is dense with
 * framework namespace literals, and a library pack containing those is not
 * framework-agnostic -- a Micronaut or Quarkus pack depending on it would
 * inherit them.
 *
 * The figure is NOT quoted here, and quoting it is a check failure. Successive
 * drafts carried different values because each was hand-derived from an unpinned
 * grep while doing rhetorical work inside an architectural rationale. Run
 * `harness/check-invariants.py`, which pins the patterns in code and prints the
 * current counts; check 6 fails the build if any doc or comment reintroduces a
 * hardcoded figure.
 *
 * The reviewer's criterion was narrower -- "Annotations.qll must not import
 * Catalog" -- and satisfying that alone would have left the CLAIM the criterion
 * exists to protect still false. Fixing the letter of a review comment while the
 * property it guards stays broken is the failure mode worth naming here.
 *
 * `java-signals-lib` now holds only language-level machinery: Schema (row shape),
 * Types (generic-safe matching), Annotations (meta resolution + the
 * MetaAnnotationEdges extension point). Nothing in it names a framework outside
 * a doc comment.
 *
 * Framework signature catalog.
 *
 * A single fact table keyed on (framework, package, simple name), carrying the
 * `kind` a query filters on and the `generation` a burndown metric reports.
 *
 * WHY A PLAIN QL FACT TABLE AND NOT A DATA EXTENSION
 * CodeQL model packs / `extensible predicate` are the eventual home for this
 * once (a) the catalog outgrows roughly a couple hundred tuples or (b) someone
 * who does not write QL needs to edit it. Today neither holds, model packs are
 * still public preview, and a plain predicate compiles on every CLI version.
 * The tuple shape below is deliberately data-extension-shaped so the migration
 * is mechanical. See docs/CAMPAIGN.md wave 5.
 *
 * GENERATION VALUES
 *   "javax"      Jakarta EE 8 / Java EE namespace -- Boot <= 2.7
 *   "jakarta"    Jakarta EE 9+ namespace -- Boot >= 3.0
 *   "hibernate5" Hibernate ORM 5.x semantics -- Boot <= 2.7
 *   "hibernate6" Hibernate ORM 6.x semantics -- Boot >= 3.0
 *   "swagger2"   Swagger 2 / springfox annotations
 *   "openapi3"   OpenAPI 3 / springdoc annotations
 *   "boot2"      present in Boot 2.x, removed or relocated by Boot 4
 *   "boot3+"     introduced in Boot 3.x or later
 *   ""           not version-tracked
 *
 * An empty generation means "this rule does not track a version axis", never
 * "version unknown". If a signal needs a version axis, add the tuples; do not
 * emit a placeholder.
 */

import java

/**
 * Holds if `pkg`.`name` is a known signature of `framework`, classified as
 * `kind`, on the `generation` axis.
 */
predicate signature(string framework, string pkg, string name, string kind, string generation) {
  //
  // ---- JPA: the javax -> jakarta pair. 286 javax.persistence imports in
  // ---- ocs-api-service; this pair IS the 2.7 -> 3.0 burndown metric.
  //
  framework = "jpa" and
  generation = "javax" and
  pkg = "javax.persistence" and
  jpaAnnotationName(name, kind)
  or
  framework = "jpa" and
  generation = "jakarta" and
  pkg = "jakarta.persistence" and
  jpaAnnotationName(name, kind)
  or
  framework = "jpa" and
  kind = "transactional" and
  (
    pkg = "javax.transaction" and name = "Transactional" and generation = "javax"
    or
    pkg = "jakarta.transaction" and name = "Transactional" and generation = "jakarta"
  )
  or
  framework = "validation" and
  kind = "constraint" and
  (
    pkg = "javax.validation" and generation = "javax"
    or
    pkg = "jakarta.validation" and generation = "jakarta"
  ) and
  name in ["Valid", "Validated"]
  or
  framework = "annotation" and
  kind = "lifecycle" and
  (
    pkg = "javax.annotation" and generation = "javax"
    or
    pkg = "jakarta.annotation" and generation = "jakarta"
  ) and
  name in ["PostConstruct", "PreDestroy", "Resource"]
  or
  //
  // ---- Hibernate. @Type/@TypeDef semantics were rewritten wholesale between
  // ---- Hibernate 5 and 6, and @Where was renamed @SQLRestriction in 6.3.
  // ---- 31 sites in ocs-api-service, backed by hibernate-types-52.
  //
  framework = "hibernate" and
  pkg = "org.hibernate.annotations" and
  (
    name = "Type" and kind = "custom_type" and generation = "hibernate5"
    or
    name = "TypeDef" and kind = "custom_type" and generation = "hibernate5"
    or
    name = "TypeDefs" and kind = "custom_type" and generation = "hibernate5"
    or
    name = "Where" and kind = "filter" and generation = "hibernate5"
    or
    name = "SQLRestriction" and kind = "filter" and generation = "hibernate6"
    or
    name = "JdbcTypeCode" and kind = "custom_type" and generation = "hibernate6"
    or
    name = "JdbcType" and kind = "custom_type" and generation = "hibernate6"
    or
    name = "GenericGenerator" and kind = "id_generator" and generation = ""
    or
    name = "Fetch" and kind = "fetch" and generation = ""
    or
    name = "BatchSize" and kind = "fetch" and generation = ""
    or
    name = "Formula" and kind = "mapping" and generation = ""
    or
    name = "NaturalId" and kind = "mapping" and generation = ""
    or
    name = "DynamicUpdate" and kind = "mapping" and generation = ""
    or
    name = "CreationTimestamp" and kind = "auditing" and generation = ""
    or
    name = "UpdateTimestamp" and kind = "auditing" and generation = ""
  )
  or
  // NOTE: hibernate-types-52 (com.vladmihalcea) is deliberately NOT catalogued
  // here. An earlier draft had a wildcard branch `pkg.matches("com.vladmihalcea%")
  // and name != ""`, which does not compile -- neither `pkg` nor `name` is bound
  // by anything, so the relation is unbounded. `signature` is a FINITE fact
  // table by construction; a wildcard branch is a category error, not a typo.
  // Package-pattern matching belongs in the query (HibernateTypes.ql already
  // does it via typePackageMatches and the import regex), not in the catalog.
  //
  // The deletion originally left `or` ... comment ... `or`, i.e. an EMPTY
  // DISJUNCT, which is itself a compile error. Removing a branch means removing
  // one of its adjacent separators; a comment does not occupy the slot.
  //
  // ---- OpenAPI / Swagger. Two annotation stacks coexist in ocs-api-service:
  // ---- 148 Swagger 2 sites and 1012 OpenAPI 3 sites, 4 files carrying both.
  // ---- springfox 2.9.2 is hard-incompatible with Boot 3.
  //
  framework = "openapi" and
  generation = "swagger2" and
  pkg = "io.swagger.annotations" and
  (
    name = "ApiOperation" and kind = "operation"
    or
    name = "Api" and kind = "tag"
    or
    name = "ApiModel" and kind = "schema"
    or
    name = "ApiModelProperty" and kind = "schema"
    or
    name = "ApiResponse" and kind = "response"
    or
    name = "ApiResponses" and kind = "response"
    or
    name = "ApiParam" and kind = "parameter"
  )
  or
  framework = "openapi" and
  generation = "openapi3" and
  (
    pkg = "io.swagger.v3.oas.annotations" and name = "Operation" and kind = "operation"
    or
    pkg = "io.swagger.v3.oas.annotations" and name = "Parameter" and kind = "parameter"
    or
    pkg = "io.swagger.v3.oas.annotations.tags" and name = "Tag" and kind = "tag"
    or
    pkg = "io.swagger.v3.oas.annotations.media" and name = "Schema" and kind = "schema"
    or
    pkg = "io.swagger.v3.oas.annotations.media" and name = "ArraySchema" and kind = "schema"
    or
    pkg = "io.swagger.v3.oas.annotations.media" and name = "Content" and kind = "content"
    or
    pkg = "io.swagger.v3.oas.annotations.responses" and name = "ApiResponse" and kind = "response"
    or
    pkg = "io.swagger.v3.oas.annotations.responses" and name = "ApiResponses" and kind = "response"
    or
    pkg = "io.swagger.v3.oas.annotations.parameters" and name = "RequestBody" and kind = "parameter"
  )
  or
  //
  // ---- Spring Web mapping annotations. Untracked generation: these are
  // ---- stable from Boot 2.7 through 4.x.
  //
  framework = "spring" and
  generation = "" and
  pkg = "org.springframework.web.bind.annotation" and
  (
    name = "RequestMapping" and kind = "mapping_any"
    or
    name = "GetMapping" and kind = "mapping_get"
    or
    name = "PostMapping" and kind = "mapping_post"
    or
    name = "PutMapping" and kind = "mapping_put"
    or
    name = "PatchMapping" and kind = "mapping_patch"
    or
    name = "DeleteMapping" and kind = "mapping_delete"
    or
    name = "ResponseStatus" and kind = "response_status"
    or
    name = "ResponseBody" and kind = "response_body"
    or
    name = "CrossOrigin" and kind = "cors"
    or
    name = "ExceptionHandler" and kind = "exception_handler"
    or
    name = "ControllerAdvice" and kind = "advice"
    or
    name = "RestControllerAdvice" and kind = "advice"
    or
    name = "RestController" and kind = "controller"
    or
    name = "RequestParam" and kind = "param_binding"
    or
    name = "PathVariable" and kind = "param_binding"
    or
    name = "RequestBody" and kind = "param_binding"
    or
    name = "RequestHeader" and kind = "param_binding"
    or
    name = "RequestPart" and kind = "param_binding"
    or
    name = "CookieValue" and kind = "param_binding"
  )
  or
  // Spring 6.1 / Boot 3.2 HTTP interface clients. Absent from ocs-api-service
  // today; catalogued now because they are the migration target for the one
  // @FeignClient, and because a burndown needs both endpoints of the move.
  framework = "spring" and
  generation = "boot3+" and
  pkg = "org.springframework.web.service.annotation" and
  kind = "http_exchange" and
  name in [
      "HttpExchange", "GetExchange", "PostExchange", "PutExchange", "PatchExchange",
      "DeleteExchange"
    ]
  or
  framework = "spring" and
  generation = "boot2" and
  pkg = "org.springframework.cloud.openfeign" and
  kind = "feign" and
  name in ["FeignClient", "EnableFeignClients"]
  or
  //
  // ---- Spring stereotypes and configuration.
  //
  framework = "spring" and
  generation = "" and
  (
    pkg = "org.springframework.stereotype" and
    name in ["Service", "Component", "Repository", "Controller"] and
    kind = "stereotype"
    or
    pkg = "org.springframework.context.annotation" and
    name in ["Configuration", "Bean", "Import", "ComponentScan", "Profile", "PropertySource"] and
    kind = "config"
    or
    pkg = "org.springframework.boot.autoconfigure" and
    name = "SpringBootApplication" and
    kind = "config"
    or
    pkg = "org.springframework.boot.context.properties" and
    name in ["ConfigurationProperties", "EnableConfigurationProperties", "ConfigurationPropertiesScan"] and
    kind = "config_properties"
    or
    pkg = "org.springframework.beans.factory.annotation" and
    name in ["Value", "Autowired", "Qualifier"] and
    kind = "injection"
    or
    pkg = "org.springframework.cache.annotation" and
    name in ["Cacheable", "CacheEvict", "CachePut", "Caching", "CacheConfig", "EnableCaching"] and
    kind = "cache"
    or
    pkg = "org.springframework.scheduling.annotation" and
    name in ["Async", "EnableAsync", "Scheduled", "EnableScheduling"] and
    kind = "async"
    or
    pkg = "org.springframework.transaction.annotation" and
    name in ["Transactional", "EnableTransactionManagement"] and
    kind = "transactional"
    or
    pkg = "org.springframework.data.jpa.repository" and
    name in ["Query", "Modifying", "EntityGraph"] and
    kind = "data_query"
    or
    pkg = "org.springframework.data.repository.query" and
    name = "Param" and
    kind = "data_query"
  )
  or
  // Spring Data JPA 3.4+ replacement for @Query(nativeQuery = true).
  framework = "spring" and
  generation = "boot3+" and
  pkg = "org.springframework.data.jpa.repository" and
  name = "NativeQuery" and
  kind = "data_query"
}

/** Holds if `name` is a JPA annotation of kind `kind`, in either namespace. */
private predicate jpaAnnotationName(string name, string kind) {
  name = "Entity" and kind = "entity"
  or
  name = "MappedSuperclass" and kind = "entity"
  or
  name = "Embeddable" and kind = "entity"
  or
  name = "Table" and kind = "table"
  or
  name = "SecondaryTable" and kind = "table"
  or
  name = "Column" and kind = "column"
  or
  name = "JoinColumn" and kind = "join"
  or
  name = "JoinTable" and kind = "join"
  or
  name = "ManyToOne" and kind = "relation"
  or
  name = "OneToMany" and kind = "relation"
  or
  name = "ManyToMany" and kind = "relation"
  or
  name = "OneToOne" and kind = "relation"
  or
  name = "Id" and kind = "id"
  or
  name = "EmbeddedId" and kind = "id"
  or
  name = "Embedded" and kind = "mapping"
  or
  name = "GeneratedValue" and kind = "id"
  or
  name = "Version" and kind = "locking"
  or
  name = "Enumerated" and kind = "mapping"
  or
  name = "Lob" and kind = "mapping"
  or
  name = "Temporal" and kind = "mapping"
  or
  name = "Transient" and kind = "mapping"
  or
  name = "Convert" and kind = "mapping"
  or
  name = "ElementCollection" and kind = "mapping"
  or
  name = "EntityListeners" and kind = "lifecycle"
  or
  name = "PrePersist" and kind = "lifecycle"
  or
  name = "PreUpdate" and kind = "lifecycle"
  or
  name = "PostLoad" and kind = "lifecycle"
  or
  name = "NamedQuery" and kind = "named_query"
  or
  name = "NamedQueries" and kind = "named_query"
  or
  name = "NamedNativeQuery" and kind = "named_native_query"
  or
  name = "NamedNativeQueries" and kind = "named_native_query"
  or
  name = "SqlResultSetMapping" and kind = "result_set_mapping"
  or
  name = "SqlResultSetMappings" and kind = "result_set_mapping"
  or
  name = "ConstructorResult" and kind = "result_set_mapping"
  or
  name = "ColumnResult" and kind = "result_set_mapping"
}

/**
 * Holds if `t` is a Spring Data repository root interface.
 *
 * `PagingAndSortingRepository` stopped extending `CrudRepository` in Spring Data
 * 3.0, and `ListCrudRepository` / `ListPagingAndSortingRepository` were added in
 * the same release -- so the root set is itself generation-sensitive.
 */
predicate repositoryRoot(string pkg, string name, string generation) {
  pkg = "org.springframework.data.repository" and
  generation = "" and
  name in ["Repository", "CrudRepository", "PagingAndSortingRepository"]
  or
  pkg = "org.springframework.data.repository" and
  generation = "boot3+" and
  name in ["ListCrudRepository", "ListPagingAndSortingRepository"]
  or
  pkg = "org.springframework.data.jpa.repository" and
  generation = "" and
  name in ["JpaRepository", "JpaSpecificationExecutor"]
  or
  pkg = "org.springframework.data.querydsl" and
  generation = "" and
  name = "QuerydslPredicateExecutor"
  or
  pkg = "org.springframework.data.repository.reactive" and
  generation = "" and
  name in ["ReactiveCrudRepository", "ReactiveSortingRepository"]
  or
  pkg = "org.springframework.data.mongodb.repository" and generation = "" and name = "MongoRepository"
  or
  pkg = "org.springframework.data.r2dbc.repository" and generation = "" and name = "R2dbcRepository"
}

/**
 * Holds if `pkg`.`name` is a JDBC/SQL execution surface.
 *
 * ocs-api-service runs 26 JdbcTemplate/NamedParameterJdbcTemplate call sites
 * carrying inline SQL that no `@Query`-based rule can see.
 */
predicate sqlExecutorType(string pkg, string name, string generation) {
  // Concrete types only. Including both JdbcTemplate and JdbcOperations would
  // double-count every JdbcTemplate site, because typeIsOrExtends matches both.
  pkg = "org.springframework.jdbc.core" and
  generation = "" and
  name = "JdbcTemplate"
  or
  pkg = "org.springframework.jdbc.core.namedparam" and
  generation = "" and
  name = "NamedParameterJdbcTemplate"
  or
  pkg = "org.springframework.jdbc.core.simple" and generation = "boot3+" and name = "JdbcClient"
  or
  pkg = "javax.persistence" and generation = "javax" and name = "EntityManager"
  or
  pkg = "jakarta.persistence" and generation = "jakarta" and name = "EntityManager"
}


/*
 * Spring's meta-annotation edge table used to live in this file, back when this
 * file lived in java-signals-lib. It is now SpringMetaEdges.qll, a sibling in
 * this query pack, contributed to the library through its MetaAnnotationEdges
 * extension point.
 *
 * The remaining design debt is different from what an earlier version of this
 * note claimed: `signature` / `repositoryRoot` / `sqlExecutorType` are correctly
 * located now, but `generation` is still DENORMALIZED INTO THE ROW at extraction
 * time. That makes a catalog correction require a full re-extraction and makes
 * the burndown a time series whose definition can move silently. Wave 1c moves
 * `generation` to a read-time join, which dissolves the write-path coupling
 * entirely. See docs/CAMPAIGN.md.
 */

/**
 * WAVE 3 DESIGN NOTE -- JACKSON GENERATION TAGGING IS NOT A PACKAGE PREFIX.
 *
 * The obvious rule -- `com.fasterxml.jackson.*` => generation "jackson2",
 * `tools.jackson.*` => "jackson3" -- is wrong, and wrong in the direction that
 * inflates the migration backlog.
 *
 * Jackson 3 moved databind and core to `tools.jackson.*` but deliberately KEPT
 * `jackson-annotations` on the `com.fasterxml.jackson.annotation` package (and
 * the `com.fasterxml.jackson.core` group ID). So `@JsonProperty`, `@JsonView`,
 * `@JsonIgnoreProperties` and friends are UNCHANGED across Jackson 2 and 3.
 *
 * ocs-api-service has 743 Jackson annotation sites. A naive prefix rule tags
 * every one of them as pending-migration work when none of them are.
 *
 * When wave 3 lands Jackson.ql, the catalog must therefore carry:
 *   - com.fasterxml.jackson.annotation.*  => generation ""        (not tracked)
 *   - com.fasterxml.jackson.databind.*    => generation "jackson2" (pending)
 *   - com.fasterxml.jackson.core.*        => generation "jackson2" (pending)
 *   - com.fasterxml.jackson.datatype.*    => generation "jackson2" (pending)
 *   - com.fasterxml.jackson.dataformat.*  => generation "jackson2" (pending)
 *   - tools.jackson.*                     => generation "jackson3" (migrated)
 * plus the Boot-side renames: @JsonComponent -> @JacksonComponent,
 * @JsonMixin -> @JacksonMixin, Jackson2ObjectMapperBuilderCustomizer ->
 * JsonMapperBuilderCustomizer.
 *
 * The same shape of exception should be assumed to exist for any other
 * "namespace moved" migration until proven otherwise. Enumerate; do not prefix.
 */
