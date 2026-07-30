# Closing the JPA/Hibernate Predicate Vocabulary: A Bounded Completeness Survey

> **Current as of 2026-07-30.** Treat this survey as a **predicate vocabulary backlog**, not a Phase 1 implementation checklist. Vocabulary + EDB/IDB + `not-a-base-table` / contested remain useful. Integration-cost sizing into [`10-architecture-maturation-plan.md`](10-architecture-maturation-plan.md) is stale relative to the portable kernel and contested-map work already shipped. Executable Phase 1 scope was the thin dual-emit slice in [`research/fact-store-phase1-decision-memo-2026-07-30.md`](research/fact-store-phase1-decision-memo-2026-07-30.md) (**REFINE**) — **landed in PR #63** (`facts.jsonl`); do not walk this catalog as unfinished Phase 1.

> **Revised 2026-07-24 (review pass 2).** Version claims in this document are reconciled against its companion, `claude/hibernate-jakarta-fact-verification-2026-07-24.md` — read the two together. Changes in this revision: `@View` "Since" resolved to **6.3** (the prior 6.3–6.4 hedge is struck); `@SoftDelete` `@Incubating` status re-confirmed against **7.4** rather than 7.1; the `@Where` removal now cites Hibernate's own 7.0 migration guide rather than the Quarkus guide; the javax→jakarta package move corrected to Hibernate **6.0**; the Jakarta Persistence 3.2 date softened to "April 2024" with the source discrepancy noted; **Stage 2's `persistence_unit` promoted from qualifier to fact key**; a downstream disposition defined for `UNKNOWN_HIBERNATE_ANNOTATION`; and a new "Integration cost" section recording two sizing items this survey creates for `claude/10-architecture-maturation-plan.md`.

## TL;DR
- The draft vocabulary is missing an entire effect category — **row-visibility predicates** (`@SQLRestriction`, `@SoftDelete`, `@Filter`, `@Immutable`, `@Subselect`, `@SQLSelect/@SQLInsert/@SQLUpdate/@SQLDelete`, `@Formula`) — that silently rewrite the SQL a repository emits without changing which tables exist; they survive a schema-arity fix entirely and must each be enumerated as first-class predicates.
- **Two must-cover assumptions were wrong and are corrected here:** `@Where` was not merely deprecated — it was **removed in Hibernate 7.0** (deprecated since 6.3, replaced by `@SQLRestriction`); and Hibernate **does** ship a dedicated `@View` annotation (`org.hibernate.annotations`, `@Incubating`, **since 6.3**), so it — not only `@Subselect` — is a view-mapping mechanism. `@SoftDelete` was introduced in 6.4 and is **still `@Incubating` in 7.4**, the current stable line.
- Adopt Hibernate's own `org.hibernate.mapping` model class names as the primary vocabulary (`Table`, `Column`, `ForeignKey`, `UniqueKey`, `Index`, `Join`, `PersistentClass`, `Collection`, `Component`), separate **base (per-match) facts** from **derived (cross-file resolution) facts** using the Datalog/CodeQL **EDB-vs-IDB** distinction, and add a third reconciliation verdict **`not-a-base-table`** so views/subselects are never marked "contested." Persistence-unit assignment is largely **not statically determinable** without a classpath and must become interview questions.

## Key Findings

**1. There is a missing effect category, and it is the whole point of the survey.** The draft vocabulary covers structure (tables, inheritance, relationships) but has no predicate for row-level restrictions. Hibernate has a large family of annotations that inject SQL predicates or replace whole DML statements at runtime. These do not change the set of tables; they change which rows a repository method sees or writes. A tool that models only `ClassName -> TableName` is blind to all of them, and a unary→n-ary arity fix does not surface them unless predicates are explicitly minted. Hibernate's `@SQLRestriction` Javadoc is explicit about the invisibility: "@SQLRestrictions are always applied and cannot be disabled. Nor may they be parameterized."

**2. Version facts must be pinned to Hibernate 7.x / Jakarta Persistence 3.2.** As of mid-2026 the current stable line is **7.4, latest 7.4.6.Final** ("Version 7.4.6.Final — Last updated 2026-07-19"), with 7.3 and 6.6 in limited support and 8.0 in development (8.0.0.Beta1, 2026-06-16, targeting Jakarta Persistence 4.0). **Hibernate ORM 7.0.0.Final released May 19, 2025** and migrated to **Jakarta Persistence 3.2** (finalized **April 2024** — see the dating caveat below). Several Hibernate-native annotations were deprecated in 6.3 and **removed in 7.0**. **The `javax.persistence.*` → `jakarta.persistence.*` package move was Hibernate 6.0 (JPA 3.0), not 7.0** — do not attribute it to the 7.0 line; 7.0's Jakarta step was the 3.1→3.2 upgrade. Because the tool reads facts across versions, it must record which Hibernate/Jakarta baseline it assumed on each scan.

**3. Prior art exists for both the vocabulary and the base/derived layering — use it rather than inventing names.** Hibernate's own configuration-time mapping model (`org.hibernate.mapping`) is the fully-resolved target that static extraction approximates; its class names are the strongest candidate vocabulary. jQAssistant's JPA plugin publishes concrete Neo4j labels. CodeQL, Glean, and Datalog all formalize exactly the raw-fact vs derived-fact split the tool needs.

---

## Details

### A. The catalog, grouped by effect category

Effect categories: **(1)** which tables exist; **(2)** which rows are visible; **(3)** identity/constraints; **(4)** namespace; **(5)** relationships. Columns: name · package · status/version · arity/dimensions · per-match vs cross-file · no-preimage/phantom flag · statically determinable.

#### Category 2 — ROW VISIBILITY (the reason for the survey)

| Name | Package | Status / Version | Arity / dimensions | Per-match vs cross-file | Preimage flag | Statically determinable |
|---|---|---|---|---|---|---|
| `@SQLRestriction` | `org.hibernate.annotations` | Current; **since 6.3**; stable (not `@Incubating`) | (subject, RESTRICTED_BY, sqlPredicate) + qualifier applies-to (entity vs collection) | Per-match | neither | Yes — literal SQL string |
| `@Where` | `org.hibernate.annotations` | **Deprecated 6.3 (`@Deprecated(since="6.3")`), REMOVED in 7.0** → `@SQLRestriction` | same as `@SQLRestriction` | Per-match | neither | Yes; its presence in 7.x source is itself an error signal |
| `@WhereJoinTable` | `org.hibernate.annotations` | **Removed 7.0** → `@SQLJoinTableRestriction` | (join-table, RESTRICTED_BY, predicate) | Per-match | neither | Yes |
| `@SQLJoinTableRestriction` | `org.hibernate.annotations` | Current; since 6.3 | join-table row predicate | Per-match | neither | Yes |
| `@SoftDelete` | `org.hibernate.annotations` | **Introduced 6.4; still `@Incubating` in 7.4** | (subject, SOFT_DELETED_BY, columnName) + qualifiers strategy (DELETED/ACTIVE), converter | Per-match at class; **cross-file** when on `package-info.java` or applied to a `SINGLE_TABLE` hierarchy root | neither | Yes for column/strategy; hierarchy scope needs sibling resolution |
| `@Filter` / `@FilterDef` / `@ParamDef` | `org.hibernate.annotations` | Current | (subject, FILTERED_BY, filterName) + (filterName, HAS_CONDITION, sql) + params; **active only if `session.enableFilter(...)` is called** | **Cross-file**: `@FilterDef` may be on a different type/package than the `@Filter` referencing it by name; activation is in Java service code | neither | Partially — definition/attachment yes; whether it is ever enabled is a runtime fact |
| `@FilterJoinTable` | `org.hibernate.annotations` | Current | join-table filter | Cross-file (name ref) | neither | Partially |
| `@Immutable` | `org.hibernate.annotations` | Current | (subject, IS_IMMUTABLE, true) — suppresses UPDATE/DELETE | Per-match | neither | Yes |
| `@Subselect` | `org.hibernate.annotations` | Current | (subject, MAPPED_TO_SUBSELECT, sqlQuery) — entity maps to an inline query, **not a base table** | Per-match; the tables it reads come from `@Synchronize` | **PHANTOM TABLE** (entity owns no physical table) | Yes — SQL is literal |
| `@Synchronize` | `org.hibernate.annotations` | Current | (subject, SYNCHRONIZES_WITH, tableName[]) — real tables the subselect/view depends on | Per-match | names real tables that DO have preimages elsewhere | Yes — literal table names |
| `@View` | `org.hibernate.annotations` | **`@Incubating`; Since 6.3** (confirmed against the Javadoc "Since" field on the 6.3 package-summary index and every later line through 7.4) | (subject, MAPPED_TO_VIEW, sqlQuery); view name from `@Table`; **DDL-exportable** unlike `@Subselect` | Per-match | entity is a **PHANTOM** (no base table); the object it maps to is a **VIEW, not a base table** | Yes |
| `@SQLSelect` | `org.hibernate.annotations` | Current | (subject, CUSTOM_SELECT, sql) | Per-match | neither | Yes |
| `@SQLInsert` / `@SQLUpdate` / `@SQLDelete` / `@SQLDeleteAll` | `org.hibernate.annotations` | Current | (subject, CUSTOM_{INSERT,UPDATE,DELETE}, sql) + qualifiers callable, check style | Per-match | neither | Yes — often reveals soft-delete-by-UPDATE and stored-procedure calls |
| `@Formula` | `org.hibernate.annotations` | Current | (subject.attr, COMPUTED_BY, sqlExpr) — a read-only computed value | Per-match | column with no physical-column preimage | Yes |
| `@DiscriminatorFormula` | `org.hibernate.annotations` | Current | (subject, DISCRIMINATED_BY_FORMULA, sqlExpr) — replaces the discriminator column | Per-match; semantics require knowing the hierarchy | neither | Yes for the formula string |
| `@Any` / `@AnyDiscriminator` / `@AnyKeyJavaClass` / `@AnyDiscriminatorValue` | `org.hibernate.annotations` | Current | polymorphic association resolved by a discriminator column to one of several tables | **Cross-file**: target entities/tables are other classes | neither | Partially — discriminator mapping yes; targets need resolution |
| `@NaturalId` | `org.hibernate.annotations` | Current | (subject.attr, IS_NATURAL_ID) — candidate key; adds a unique constraint + query path, does not itself filter rows | Per-match | neither (also Category 3) | Yes |
| `@NotFound` | `org.hibernate.annotations` | Current | association-load behavior (IGNORE suppresses errors/rows) | Per-match | neither | Yes |

`@Where`/`@SQLRestriction`/`@Filter`/`@SoftDelete` are exactly the constructs the review flagged as "change which rows a table has, not which tables exist." Each needs a predicate.

#### Category 1 — WHICH TABLES EXIST

| Name | Package | Status | Arity / dimensions | Per-match vs cross-file | Preimage flag | Static? |
|---|---|---|---|---|---|---|
| `@Entity(name=)` | `jakarta.persistence` | Current (3.2) | (class, IS_ENTITY, entityName) — `name` is the **JPQL** name, not the table | Per-match | — | Yes |
| `@Table(name=, schema=, catalog=, uniqueConstraints=, indexes=)` | `jakarta.persistence` | Current | (class, MAPS_TO_TABLE, table) + qualifiers schema/catalog + nested UNIQUE/INDEX facts | Per-match | — | Yes |
| `@SecondaryTable(s)` | `jakarta.persistence` | Current | (class, ALSO_MAPS_TO_TABLE, table2) — one entity → 2+ tables | Per-match | second table has a preimage, but not via a 1:1 map | Yes |
| `@MappedSuperclass` | `jakarta.persistence` | Current | (class, IS_MAPPED_SUPERCLASS) — owns **no table**; columns flow to subclasses | **Cross-file**: physical effect only on subclasses | **PHANTOM** (no table of its own) | Yes to detect; effect needs subclasses |
| `@Inheritance(SINGLE_TABLE)` | `jakarta.persistence` | Current (default) | subclasses share ONE root table | **Cross-file**: subclasses in other files map to the root table; per-subclass table names are fiction | subclass entities → **phantom** per-subclass tables | Root yes; suppression of subclass tables needs the sibling set |
| `@Inheritance(JOINED)` | `jakarta.persistence` | Current | each class → its own table joined by PK/FK | **Cross-file** | each class has a real table | Yes per class; join structure cross-file |
| `@Inheritance(TABLE_PER_CLASS)` | `jakarta.persistence` | Current (optional in spec) | each concrete class → own table; abstract root owns **no** table | **Cross-file** | abstract root → **phantom table** | Root abstractness + concreteness need class-modifier + sibling info |
| `@ElementCollection` + `@CollectionTable` | `jakarta.persistence` | Current | a side table of basic/embeddable values keyed by owner FK | Per-match (both on same field) | **TABLE WITH NO ENTITY PREIMAGE** | Yes |
| `@CollectionTable` | `jakarta.persistence` | Current | names the element-collection table | Per-match | no-entity-preimage | Yes |
| `@JoinTable` | `jakarta.persistence` | Current | association/link table (M:N or unidirectional 1:N) | Per-match | **TABLE WITH NO ENTITY PREIMAGE** | Yes (name/columns) |
| `@TableGenerator` | `jakarta.persistence` | Current | a physical id-allocation table | Per-match | **NO ENTITY PREIMAGE** | Yes |
| `@Subselect` / `@View` | `org.hibernate.annotations` | (see Cat. 2) | suppresses / substitutes a base table | Per-match | phantom / view | Yes |

#### Category 3 — IDENTITY & CONSTRAINTS

| Name | Package | Status | Arity | Per-match vs cross-file | Static? |
|---|---|---|---|---|---|
| `@Id` | `jakarta.persistence` | Current | (subject.attr, IS_ID) | Per-match | Yes |
| `@IdClass` | `jakarta.persistence` | Current | (class, HAS_ID_CLASS, otherClass) — composite key in another class | **Cross-file** (id class is a sibling type) | Yes to detect ref |
| `@EmbeddedId` | `jakarta.persistence` | Current | (subject.attr, HAS_EMBEDDED_ID, embeddableClass) | **Cross-file** (embeddable elsewhere) | Yes |
| `@Embeddable` / `@Embedded` | `jakarta.persistence` | Current | value type inlined into owner's table | **Cross-file** | Yes |
| `@AttributeOverride(s)` | `jakarta.persistence` | Current | remaps embeddable column names in this owner | Per-match | Yes |
| `@MapsId` | `jakarta.persistence` | Current | derived identity — PK is also FK | Per-match; semantics cross-file | Yes |
| `@Version` | `jakarta.persistence` | Current | (subject.attr, OPTIMISTIC_LOCK_VERSION) — adds `WHERE version=?` to writes | Per-match | Yes |
| `@GeneratedValue` | `jakarta.persistence` | Current | (subject.attr, ID_GENERATED_BY, strategy) + qualifier generator ref | Per-match; generator def may be cross-file | Yes |
| `@SequenceGenerator` | `jakarta.persistence` | Current | a DB sequence (not a table) | Per-match | Yes |
| `@TableGenerator` | `jakarta.persistence` | Current | see Cat. 1 (physical table) | Per-match | Yes |
| `@UniqueConstraint` (in `@Table`) | `jakarta.persistence` | Current | (table, HAS_UNIQUE_KEY, columns[]) | Per-match | Yes |
| `@Index` (in `@Table`) | `jakarta.persistence` | Current | (table, HAS_INDEX, columns[]) | Per-match | Yes |
| `@NaturalId` | `org.hibernate.annotations` | Current | candidate key (also Cat. 2) | Per-match | Yes |

#### Category 5 — RELATIONSHIPS

`@ManyToOne`, `@OneToMany`, `@OneToOne`, `@ManyToMany` (`jakarta.persistence`, current): (owner, CARDINALITY, target) + qualifiers owning-side, `mappedBy`, fetch. **Cross-file** to resolve the target entity's table and the owning side (`mappedBy` points at the other class). `@JoinColumn`/`@JoinColumns`, `@PrimaryKeyJoinColumn`, `@ForeignKey`, `@MapKeyJoinColumn` name FK columns (per-match). `@OrderColumn`, `@MapKeyColumn` add physical columns to a collection table.

#### Category 4 — NAMESPACE

`@Table(schema=, catalog=)`, `@SecondaryTable(schema=)`, `jakarta.persistence.@PersistenceContext(unitName=)`, `@PersistenceUnit(unitName=)`, persistence.xml `<persistence-unit>`, and Spring's `@EnableJpaRepositories(entityManagerFactoryRef=, transactionManagerRef=, basePackages=)`. Treated as a first-class tuple-shape decision below.

### B. Namespace / multi-datasource — what is and is not statically determinable

Every fact needs a **persistence-unit / namespace dimension**, because the same `ClassName -> TableName` mapping can exist in two datasources with different physical schemas.

- **`schema=` / `catalog=` on `@Table`**: statically determinable per-match (literal strings). Store as **qualifiers** on the `MAPS_TO_TABLE` fact.
- **persistence.xml `<persistence-unit>`**: statically determinable — it names the unit, transaction-type, provider, and (sometimes) explicit `<class>` entries. jQAssistant models exactly this (a `PersistenceUnit` node with `CONTAINS` edges to listed entity types). When classes are listed explicitly, unit membership **is** a fact.
- **Spring `@EnableJpaRepositories(basePackages=, entityManagerFactoryRef=)`**: the routing rule ("repositories in this package use this EntityManagerFactory") is statically visible, but binding an `@Entity` to a unit requires knowing which `LocalContainerEntityManagerFactoryBean` scanned its package via `.packages(...)` / `.setPackagesToScan(...)` in a `@Configuration` class — a **cross-file resolution** joining the entity's package to a bean method's string/class argument. In the canonical pattern, one `@EnableJpaRepositories` and one `EntityManagerFactory` bean exist per datasource, with `@Primary` marking the default; that structure is visible in source.
- **NOT statically determinable from source alone**: (a) the Spring Boot default single-datasource case, where one `EntityManagerFactory` is auto-configured and entities are found by classpath scanning with no explicit package list — no source artifact names the binding; (b) which physical database/URL a unit points at (in `application.yml`/env/secrets, possibly runtime-resolved); (c) whether a Hibernate `@Filter` is ever enabled. These are **interview questions**, not facts.

**Recommendation**: model persistence-unit membership as a fact **only** when anchored to an explicit source artifact (a persistence.xml `<class>` entry, or an `@EntityScan`/`.packages(Entity.class)` reference). Otherwise emit a low-confidence "assumed default unit" fact flagged for interview. See Stage 2 for why the unit nonetheless belongs in the fact **key** even when its value is the assumed-default sentinel.

### C. The `@Subselect`/view reconciliation problem — and the third verdict

The tool reconciles JPA-derived table facts against `CREATE TABLE` in Flyway/Liquibase migrations (sqlglot) and marks disagreements "contested." Constructs that legitimately map to something that is **not a base table** break the binary agree/disagree model:

- **`@Subselect`** — entity maps to an inline SQL query; no table, no `CREATE TABLE`. Its Javadoc: "This is an alternative to defining a view and mapping the entity to the view using the `@Table` annotation."
- **`@View`** — entity maps to a database view: "Maps an entity to a database view … allowing the view to be exported by the schema management tooling." Appears as `CREATE VIEW` in migrations, never `CREATE TABLE`.
- **`@Formula`** — a value with no physical column.
- **`@MappedSuperclass`**, **abstract `TABLE_PER_CLASS` root** — class owns no table (phantom).
- **`@ElementCollection` / `@JoinTable` / `@TableGenerator`** — the opposite shape: a real `CREATE TABLE` that no `ClassName` maps to (no entity preimage).

**Answer**: add a **third reconciliation verdict** — `not-a-base-table` (equivalently `reconciled-as-view`). The reconciler should:
1. Parse `CREATE VIEW` distinctly from `CREATE TABLE` (sqlglot exposes them as different node types).
2. Detect view/subselect entities from `@Subselect` and `@View` **only**, cross-checking the `@Synchronize` table list against real base tables. The two behave differently and the rule must not conflate them: **`@Subselect` is self-evidencing** — the query lives inline in the annotation, so there is legitimately no `CREATE VIEW` anywhere in the migrations and none should be required; **`@View` is DDL-exportable**, so it can and should be corroborated against a matching `CREATE VIEW`.

   **Do NOT use `@Immutable` + no-`@Table` as a view signal.** `@Immutable` only suppresses UPDATE/DELETE for an entity; it says nothing about whether a physical table exists. Read-only reference data (country codes, currency tables, status lookups) on implicit naming is an ordinary, common mapping to a perfectly real table. Treating it as `not-a-base-table` makes the reconciler stop expecting a `CREATE TABLE`, so a genuinely missing or renamed migration is silently swallowed as "expected, it's a view" — a false negative in precisely the signal this third verdict was introduced to protect, running in the opposite direction from the false positive it fixes.
3. When a JPA entity has no base table AND there is a matching `CREATE VIEW` (or the entity is `@Subselect`/`@View`), emit `not-a-base-table` (a distinct form of agreement), **not** `contested`.
4. Symmetrically, a `CREATE TABLE` with no entity preimage that matches a `@JoinTable`/`@CollectionTable`/`@TableGenerator` name is **reconciled**, not orphaned.

### D. Prior art for the vocabulary

**Hibernate `org.hibernate.mapping` (strongest candidate — the fully-resolved model static extraction approximates).** Package doc (7.0 Javadocs): the objects represent "Java elements with a persistent representation, for example, a `PersistentClass`, `Collection`, or `Property`, and objects in a relational database, for example, a `Table`, `Column`, or `ForeignKey`," and are "passed to the schema export tooling which uses them directly to produce DDL." Concrete class names to mirror as predicates/node types: `PersistentClass` (+ subtypes `RootClass`, `SingleTableSubclass`, `JoinedSubclass`, `UnionSubclass`), `Table`, `Column`, `Formula`, `ForeignKey`, `UniqueKey`, `Index`, `PrimaryKey`, `Join`, `Collection` (+ `Bag`, `Set`, `List`, `Map`, `Array`), `Property`, `Component` (embeddable), `Any` (+ `Any.MetaValue`), `Value`, `DependantValue`, `CheckConstraint`, `AggregateColumn`, `Backref`. This is a Red Hat-maintained, actively developed model (Hibernate ORM 7.4, Javadoc "Copyright © 2001-2026 Red Hat, Inc."); it is authoritative and version-stable, and it is the vocabulary the extraction is approximating.

**jQAssistant JPA plugin (concrete Neo4j labels, read from source).** The archived `jqa-jpa2-plugin` (superseded by `jqassistant-jee-plugin`) uses these labels/relationships, verified from its rule XML (`jpa2.xml`) and descriptor interfaces:
- Node labels: `Jpa` (marker), `Entity`, `Embeddable`, `Embedded`, `EmbeddedId`, `NamedQuery`, `PersistenceUnit`, `Persistence` (the persistence.xml file).
- `PersistenceUnitDescriptor` carries properties `transactionType`, `provider`, `jtaDatasource`, `nonJtaDatasource`, `validationMode`, `sharedCacheMode`, and relationships `CONTAINS` (→ entity `TypeDescriptor`) and `HAS` (→ properties).
- Relationships: `DEFINES` (entity → `NamedQuery`), on top of the Java-plugin base relations `ANNOTATED_BY`, `OF_TYPE`, `DECLARES`.
- Maturity signal: the jpa2 repo shows **0 stars, 1 fork, 1 watching, and was archived April 21, 2023**; its label set is **shallow** — it never modeled tables, columns, or row filters, precisely the gap this survey fills. Use it as a naming precedent only, not a model to mirror wholesale.

**SCIP `Relationship` (the shape the fact store is modeled on).** `scip.proto` defines a `Relationship` message with boolean flags `is_implementation`, `is_reference`, `is_type_definition`, `is_definition` keyed by a `symbol` string — the (subject, predicate-as-flags, object) precedent for the n-ary record. Example from the schema comment: `relationships = [{symbol: "Animal#sound()", is_implementation:true, is_reference: true}]`.

### E. Base facts vs derived facts — the terminology to adopt

All three named systems formalize the same split; adopt the Datalog terms as the architecture's names because they are the lingua franca the others cite.

- **Datalog: EDB vs IDB.** "EDB = Extensional Database = stored table. IDB = Intensional Database = relation defined by rules." EDB predicates appear only in rule bodies (inputs); IDB predicates appear in rule heads (derived) — "Never both! No EDB in heads." Obligations: **stratification** ("A Datalog program P is stratified if its rules can be partitioned into strata P₁,…,Pₙ such that if a predicate p occurs in a positive (negative) literal…"), and evaluation ordering so each IDB predicate is computed after its body predicates. A cited caution from an incremental-Datalog engine: "once merged, the facts from EDBs and IDBs can not be distinguished … recomputation is highly inefficient and does not match with an incremental approach" — i.e., keep the two layers separately tagged.
- **CodeQL: extensional vs intensional predicates.** From CodeQL's own publication: extensional relations "are defined explicitly by storing their extent (that is, the tuples they contain) in the database. This contrasts with intensional relations that are defined implicitly by QL predicates and evaluated on top of the database." Mechanism: language extractors emit `.trap` files → a trap importer builds the **extensional database**; the QL compiler/solver derives the **intensional database**.
- **Glean: raw (indexer-produced) facts vs derived predicates.** Glean distinguishes facts "generated by an indexer" from **derived predicates**, of which there are two kinds: **`stored`** (materialized into a stacked DB by a query at derivation time) and **on-demand** (computed at query time). Glean uses derived predicates "to encapsulate complex queries … even building up libraries representing whole abstraction layers over the raw data" (its language-neutral `codemarkup` schema is the example).

**Mapping to the tool**: raw per-match ast-grep emissions = **EDB / base / raw facts**. The whole-store resolution pass = **IDB / derived / stored-derived predicates**: suppress fabricated per-subclass `SINGLE_TABLE` tables once siblings are known; mark abstract `TABLE_PER_CLASS` roots as owning no table; resolve `mappedBy` owning sides; bind `@FilterDef` names to `@Filter` uses; join entity packages to EntityManagerFactory beans. Inherited obligations: stratify derived rules (no cycles through negation), guarantee termination, **recompute derived facts when any contributing base fact changes**, and never store a derived fact without its `derived_from[]` provenance (the Datomic-style field the record already carries).

---

## Recommendations

**Stage 1 — Close the vocabulary now, versioned to Hibernate 7.x / Jakarta 3.2.** Mint these predicate families, named after `org.hibernate.mapping`:
- Structure: `MAPS_TO_TABLE`, `ALSO_MAPS_TO_TABLE` (secondary), `DEFINES_COLLECTION_TABLE`, `DEFINES_JOIN_TABLE`, `DEFINES_GENERATOR_TABLE`, `IS_MAPPED_SUPERCLASS`, `INHERITANCE_SINGLE_TABLE` / `_JOINED` / `_TABLE_PER_CLASS`, `DISCRIMINATED_BY` (+ `_FORMULA`), `MAPPED_TO_SUBSELECT`, `MAPPED_TO_VIEW`.
- **Row visibility (the new category)**: `RESTRICTED_BY` (SQLRestriction/Where), `FILTERED_BY` (+ `FILTER_DEF` / `FILTER_PARAM`), `SOFT_DELETED_BY`, `IS_IMMUTABLE`, `CUSTOM_SELECT` / `CUSTOM_INSERT` / `CUSTOM_UPDATE` / `CUSTOM_DELETE`, `COMPUTED_BY` (Formula), `SYNCHRONIZES_WITH`.
- Identity/constraints: `IS_ID`, `HAS_ID_CLASS`, `HAS_EMBEDDED_ID`, `HAS_UNIQUE_KEY`, `HAS_INDEX`, `OPTIMISTIC_LOCK_VERSION`, `ID_GENERATED_BY`, `IS_NATURAL_ID`, `DERIVES_ID` (MapsId).
- Relationships: `MANY_TO_ONE` / `ONE_TO_MANY` / `ONE_TO_ONE` / `MANY_TO_MANY`, `JOIN_COLUMN`, `FOREIGN_KEY`.

Keep the vocabulary **closed but extensible**: version it, and reserve an `UNKNOWN_HIBERNATE_ANNOTATION` catch-all fact (carrying the raw annotation FQN) so an unmodeled construct is recorded rather than dropped — avoiding a forced schema bump for every new Hibernate annotation.

**Stage 1a — `UNKNOWN_HIBERNATE_ANNOTATION`'s downstream disposition (required, not optional).** A catch-all fact carries a resolvable citation but no semantics, so all three downstream consumers need a defined behaviour or the catch-all either leaks noise into generated docs or silently reproduces the drop it exists to prevent:
- **Doc-writer (grounding-by-construction contract):** an `UNKNOWN` fact is **never citable as support for a prose claim** — it has no predicate meaning to assert. It is admissible in exactly one place: the Phase 4.1 negative-space section, rendered as "annotations present in this file that static analysis does not model: `@Foo` (path:line)."
- **The 2.1.4 hard gate:** its citation **must still resolve** to a real file and line — it is a real match, and an unresolvable one is as much a bug as any other. But it can never be the sole support for an `[Evidenced — …]` tag, because the gate checks citation resolution, not semantic adequacy; the doc-writer rule above is what prevents that.
- **Drift checker:** a *newly appearing* `UNKNOWN` fact is a **non-gating warning** — it signals the vocabulary needs extension, not that documentation went stale, and failing the build on "Hibernate shipped an annotation we don't model yet" would make every upstream release a red CI. A *disappearing* one is a no-op. Both feed a vocabulary-coverage counter so the gap is visible and trending rather than invisible.

**Stage 2 — Add the arity dimensions to the tuple, with `persistence_unit` in the KEY.** Require these named dimensions: `schema`, `catalog`, `applies_to` (entity vs collection vs join-table), and `hibernate_version_assumed` as `qualifiers{}`; and **`persistence_unit` as part of the fact's identity, not a qualifier.**

The reasoning is a correctness constraint, not a preference. Conflict detection — `0.3.1`'s simple-name collision check and `1.2.2`'s append-and-mark-`contested` rule — keys on fact identity. In a valid multi-datasource repo the persistence unit *is* the disambiguator, so a key that omits it reports two correct, intentionally-parallel mappings as an ambiguity, and the `contested` signal degrades exactly where it is most needed. Deferring this is not available either: `1.1.4` makes the record a cross-version data contract and `1.5.2` has the drift checker refuse a mismatched baseline, so promoting a qualifier into the key later is a breaking schema change that invalidates every stored baseline. It goes in from the start, nullable, with an explicit `assumed-default` sentinel when Section B's static-determinability test fails.

*(This supersedes the earlier draft of this stage, which placed `persistence_unit` in `qualifiers{}` and deferred promotion to a benchmark. That deferral contradicted the analysis that commissioned this survey and is withdrawn.)*

**Stage 3 — Split base vs derived and add the resolution pass.** Tag each fact `layer: base|derived`. Implement the derived pass in pure Python (a stratified fixpoint over the fact store — no new service, stdlib only). First derived rules: SINGLE_TABLE subclass-table suppression, TABLE_PER_CLASS abstract-root phantom marking, `mappedBy` owning-side resolution, `@FilterDef`→`@Filter` name binding, and persistence-unit binding. Recompute derived facts whenever base facts change; keep base and derived facts distinguishable for incremental recomputation.

**Stage 4 — Add the third reconciliation verdict.** Extend the reconciler to `{agree, disagree, not-a-base-table}`; parse `CREATE VIEW` distinctly in sqlglot; treat `@Subselect`/`@View`/phantom entities and no-preimage tables as reconciled, not contested.

**Interview-question list (statically unreachable — do not heuristic-guess):**
1. Which physical database/URL each persistence unit resolves to (config/env/secrets).
2. In a Spring Boot default single-datasource app, the entity↔unit binding when there is no explicit `@EntityScan` / `.packages(...)`.
3. Whether each Hibernate `@Filter` is ever enabled at runtime (`session.enableFilter`), and with what parameters.
4. The runtime `hibernate.hbm2ddl.auto` value (whether Hibernate itself creates/updates tables vs migrations owning the schema).
5. Whether a `@SQLInsert`/`@SQLDelete` custom statement targets a stored procedure (`callable=true`) whose body is outside the repo.

**Benchmarks that change the plan:** if `@Filter` usage is common in a real target repo, add a runtime-config scan (application properties / aspect) before treating filters as low-value. If Hibernate 8.0 ships and promotes `@SoftDelete`/`@View` out of `@Incubating` or removes more deprecated annotations, bump the vocabulary version and re-baseline. (The former "promote `persistence_unit` to the key if overlapping table names appear" benchmark is removed — Stage 2 now does this unconditionally.)

## Integration cost — two open items for `claude/10-architecture-maturation-plan.md`

Recorded here rather than left implicit, because both invalidate sizing estimates made before this survey existed:

1. **Phase 1 needs re-estimating.** Its ~2–3 week figure was set when the resolution work was scoped as SINGLE_TABLE sibling-awareness and `mappedBy` owning-side resolution. This survey adds at least three more cross-file derived rules — `@FilterDef`↔`@Filter` name binding, persistence-unit-to-package binding, and `@Any` discriminator target resolution — plus the stratification/fixpoint/incremental-recomputation obligations inherited from the EDB-IDB model in Section E. That is a materially larger derived pass than the estimate covers.
2. **Phase 3.6's ISP filtering was scoped against a much smaller vocabulary.** Stage 1 mints roughly thirty predicates across five categories. The row-visibility family alone is eight predicates that most repos will rarely trigger. Whether that family is subject to the same per-writer-slice filtering 3.6 establishes — or needs its own suppression pass so absent-by-default predicates do not bloat every prompt — is undecided, and 3.6's token-cost claim should not be treated as still holding until it is.

## Caveats
- **`@Incubating` annotations (`@SoftDelete`, `@View`) may change shape** across minor Hibernate releases; pin facts derived from them to the assumed version and flag them for re-verification on upgrade. Both remain `@Incubating` as of 7.4, the current stable line.
- **The removal of `@Where` in 7.0 makes version a correctness issue, not just completeness**: a repo on Hibernate 6.x may legitimately use `@Where`; the same source on 7.x will not compile. The tool must not assume a single Hibernate version — record the assumed baseline per scan. Primary source: Hibernate's own **7.0 Migration Guide**, removed-annotations list — "Removed `@Where` and `@WhereJoinTable` → use `@SQLRestriction` or `@SQLJoinTableRestriction`" — corroborated by the 6.6 Javadoc's `@Deprecated(since="6.3")` declaration on `@Where`. (The Quarkus 3.24 migration guide says the same thing but is a downstream restatement; cite Hibernate's guide.)
- **Jakarta Persistence 3.2 dating is inconsistent across official sources.** April 10, 2024 is the date printed on the spec document itself; the Eclipse project release page says April 30, 2024; the Specification Committee ballot concluded May 20, 2024; API artifact dates diverge further. Where a single figure is needed, **"April 2024"** is the safe form. Do not cite the precise day without noting which source it comes from.
- **jQAssistant's JPA label set is a naming precedent only** — archived (0 stars, 1 fork, April 2023) and it never modeled tables/columns/row-filters, so it cannot be mirrored wholesale.
- **Version anchors used throughout**: current stable Hibernate ORM **7.4.6.Final** (updated 2026-07-19), 7.3 and 6.6 in limited support, 8.0 in development (8.0.0.Beta1, 2026-06-16, targeting Jakarta Persistence 4.0); Hibernate **7.0.0.Final released May 19, 2025**; **Jakarta Persistence 3.2 finalized April 2024**. `@SQLRestriction` (6.3), `@SoftDelete` (6.4) and `@View` (6.3) "Since" tags verified against Hibernate Javadocs. Full verification record: `claude/hibernate-jakarta-fact-verification-2026-07-24.md`.
- Blog/tutorial sources were used for orientation only; every version-sensitive claim (deprecations, removals, `@Incubating` status, package names) was verified against Hibernate Javadocs, the Hibernate 7.0 migration guide, or the Jakarta Persistence spec. DeepWiki was used only for SCIP orientation and re-verified against `scip.proto`.
- "Statically determinable" assumes ast-grep on raw text with no classpath; anything requiring type resolution across JARs (e.g., resolving an `@Inheritance` strategy or embeddable declared in a dependency) degrades from a fact to an interview question.
