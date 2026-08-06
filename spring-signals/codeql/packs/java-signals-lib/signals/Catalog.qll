/**
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
  // hibernate-types-52 (vladmihalcea) is superseded by hypersistence-utils on
  // Hibernate 6. Its presence is a hard 3.x blocker, so it is catalogued as a
  // hibernate5-generation signature even though it is a third-party artifact.
  framework = "hibernate" and
  generation = "hibernate5" and
  kind = "custom_type_library" and
  pkg.matches("com.vladmihalcea%") and
  name != ""
  or
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
  pkg = "org.springframework.jdbc.core" and
  generation = "" and
  name in ["JdbcTemplate", "JdbcOperations"]
  or
  pkg = "org.springframework.jdbc.core.namedparam" and
  generation = "" and
  name in ["NamedParameterJdbcTemplate", "NamedParameterJdbcOperations"]
  or
  pkg = "org.springframework.jdbc.core.simple" and generation = "boot3+" and name = "JdbcClient"
  or
  pkg = "javax.persistence" and generation = "javax" and name = "EntityManager"
  or
  pkg = "jakarta.persistence" and generation = "jakarta" and name = "EntityManager"
}

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

/**
 * Spring's own documented meta-annotation edges, hardcoded.
 *
 * WHY THIS EXISTS -- READ BEFORE DELETING.
 *
 * `metaResolutionEnabled()` ships closed because transitive meta-resolution
 * depends on an unverified extractor assumption. Closing it was correct. But
 * closing it made `isOrMeta(a, "...stereotype", "Controller")` degrade to an
 * EXACT match on `@Controller`, which silently dropped all 48 `@RestController`
 * classes in ocs-api-service from `api_surface__controller`. The old pack
 * enumerated `@RestController` and `@Controller` explicitly and did not have
 * that hole.
 *
 * That is the real lesson: a fail-closed switch is only safe when the closed
 * state is at least as good as the baseline it replaces. Here it was strictly
 * worse -- a recall regression disguised as caution. Fixing it by reopening the
 * switch would have traded a known regression for an unverified assumption.
 *
 * So the closed state is backfilled with Spring's *documented* meta-annotation
 * graph, which is a published API contract, not an extractor inference. This is
 * exactly the "hardcode Spring's own chains and reserve the transitive
 * predicate for first-party composed annotations" fallback that was previously
 * deferred to wave 4; the regression proves it belongs in wave 1.
 *
 * The transitive predicate still buys something the table cannot: project-local
 * composed annotations. On ocs-api-service that set is empty (zero `@interface`
 * declarations), which is why the switch staying closed costs this repo nothing
 * once the table is in place.
 *
 * INVARIANT: every edge here must be verifiable from Spring source. Do not add
 * an edge because a query needs it.
 */
predicate metaEdge(string pkg, string name, string superPkg, string superName) {
  // Stereotypes. Everything composes onto @Component.
  pkg = "org.springframework.stereotype" and
  superPkg = "org.springframework.stereotype" and
  superName = "Component" and
  name in ["Service", "Repository", "Controller"]
  or
  pkg = "org.springframework.web.bind.annotation" and
  name = "RestController" and
  superPkg = "org.springframework.stereotype" and
  superName = "Controller"
  or
  pkg = "org.springframework.context.annotation" and
  name = "Configuration" and
  superPkg = "org.springframework.stereotype" and
  superName = "Component"
  or
  // Advice.
  pkg = "org.springframework.web.bind.annotation" and
  name = "ControllerAdvice" and
  superPkg = "org.springframework.stereotype" and
  superName = "Component"
  or
  pkg = "org.springframework.web.bind.annotation" and
  name = "RestControllerAdvice" and
  superPkg = "org.springframework.web.bind.annotation" and
  superName = "ControllerAdvice"
  or
  // Boot entry point and configuration variants.
  pkg = "org.springframework.boot.autoconfigure" and
  name = "SpringBootApplication" and
  superPkg = "org.springframework.context.annotation" and
  superName = "Configuration"
  or
  pkg = "org.springframework.boot.autoconfigure" and
  name = "AutoConfiguration" and
  superPkg = "org.springframework.context.annotation" and
  superName = "Configuration"
  or
  pkg = "org.springframework.boot.test.context" and
  name = "TestConfiguration" and
  superPkg = "org.springframework.context.annotation" and
  superName = "Configuration"
  or
  // HTTP method shortcuts compose onto @RequestMapping.
  pkg = "org.springframework.web.bind.annotation" and
  superPkg = "org.springframework.web.bind.annotation" and
  superName = "RequestMapping" and
  name in ["GetMapping", "PostMapping", "PutMapping", "PatchMapping", "DeleteMapping"]
  or
  // HTTP interface client shortcuts compose onto @HttpExchange.
  pkg = "org.springframework.web.service.annotation" and
  superPkg = "org.springframework.web.service.annotation" and
  superName = "HttpExchange" and
  name in ["GetExchange", "PostExchange", "PutExchange", "PatchExchange", "DeleteExchange"]
}

/** Reflexive-transitive closure of `metaEdge`. */
predicate metaReaches(string pkg, string name, string superPkg, string superName) {
  pkg = superPkg and name = superName and metaEdgeEndpoint(pkg, name)
  or
  metaEdge(pkg, name, superPkg, superName)
  or
  exists(string mp, string mn |
    metaEdge(pkg, name, mp, mn) and
    metaReaches(mp, mn, superPkg, superName)
  )
}

/** Holds if `pkg`.`name` appears anywhere in `metaEdge`, on either side. */
private predicate metaEdgeEndpoint(string pkg, string name) {
  metaEdge(pkg, name, _, _) or metaEdge(_, _, pkg, name)
}
