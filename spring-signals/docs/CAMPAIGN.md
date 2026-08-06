# spring-signals campaign

Target repo for wave 1: `ocs-api-service` @ `develop` — Spring Boot 2.7.18,
Spring Cloud 2021.0.8, Java 17 toolchain, 596 `.java` files (420 main / 176 test),
`javax.*` namespace, no annotation processors.

---

## Architectural decision

**Pack purpose: signal catalog with a version/namespace axis, split into a
language-scoped library pack plus per-framework query packs.**

This is the hybrid position, generalised so it survives the multi-language /
multi-framework expansion.

**What actually generalises, and what does not.** CodeQL library packs are
per-language — `.qll` cannot be shared between Java and Python, so "multi-language
support" cannot mean one shared QL library. What *can* be shared across languages
is the **row schema** and the **harness**. That makes the eleven-column schema in
`Schema.qll` the real product; the QL is one implementation of it. A future
`python-signals-lib` reimplements `Schema.qll` and `Annotations.qll` against
Python's stdlib and emits identical columns. So does an ast-grep rule set. The
join, the burndown, and the dashboards then work unchanged.

**What generalises across frameworks within a language** is the signature
catalog. `Catalog.qll` is keyed on `(framework, package, name, kind, generation)`,
not on Spring. Adding Micronaut or Quarkus means adding tuples plus a sibling
query pack; it does not mean forking the library.

**Why `generation` rather than `springBootGeneration`.** A Spring-specific column
name would have to be widened the first time a second framework arrived, and
schema widening is the expensive change. The axis is "which version-flavour of
this API is this", which is meaningful for Jakarta EE, Hibernate, Swagger/OpenAPI
and Jackson independently of Spring.

**Where generation is populated.** Only where it drives a burndown: `jpa`
(javax↔jakarta), `hibernate` (5↔6), `openapi` (swagger2↔openapi3), and the
handful of Spring signatures that genuinely appear or disappear across 2.7→4.x.
Everywhere else it is `""`, which means *not tracked*, never *unknown*. Blanket
tagging would be 400 tuples of ceremony to express "unchanged since 2014".

**Why a plain QL fact table and not a data extension.** CodeQL model packs are
still public preview, and the catalog is currently ~150 tuples maintained by one
person who writes QL. Data extensions earn their cost when non-QL authors need to
edit the catalog or it outgrows a few hundred tuples. The tuple shape is already
data-extension-shaped, so the migration is mechanical. Wave 5.

---

## Wave 1 — split into three merge units

Delivered as **1a / 1b / 1c**, same architecture, smaller merge units. The
original single-PR shape put the ocs acceptance tests on an uncompiled mega-diff,
which is the wrong place for them.

**Wave 1 REPLACES PR #88. Do not merge both as sequential "Wave 1."** #88
rewrote the same predicates this campaign extracts into `Types.qll` /
`Annotations.qll` / `Catalog.qll`, under a smaller contract (legacy 3-column
shape, no generation axis, `RawQueries.ql` retained, no new query files). The
double-edit the campaign was designed to avoid has already happened; the way out
is to close or rewrite #88 into this pack layout, not to land both.

### 1a — compile the foundation

Ships: `codeql-workspace.yml`, `java-signals-lib` (`Schema.qll`, `Types.qll`,
thin `Catalog.qll`), `_Common.qll`, and `Persistence.ql` only.

`Annotations.qll` ships in-tree but **disabled**: `metaResolutionEnabled()` is
defined as `none()`, so `isOrMeta` degrades to exact matching. See "trust gate"
below.

**Exit criteria — this is a merge blocker, not a footnote.**

- `codeql query compile` green against pinned `codeql/java-all` 9.2.x.
- `create-db.sh` green on `ocs-api-service @ develop`, extraction delta 0.
- The construct risk list is cleared, not deferred: `getASourceSupertype*()`
  and `getSourceDeclaration()` arities; `regexpCapture` group semantics in
  `sourceSetOf`; `MethodCall` vs `MethodAccess` naming; `TypeLiteral.getTypeName()`;
  and the `concat`-over-empty-returns-`""` idiom that makes `attr()` total.
- `probe-meta-annotations.ql` runs and its output is recorded, whether or not
  the switch is flipped.

### 1b — P0 on the new types

Ships: `Persistence.ql`, `Messaging.ql`, `OutboundClients.ql` on the v1 schema.
Supersedes #88's P0 work.

**Exit criteria.** `Persistence.ql` reports the four `BookBased*Repository`
rows the one-hop supertype walk missed, plus four `persistence__repository_marker`
rows for `BookBasedRepository`. `Messaging.ql` returns 0 and
`harness/expectations/ocs-api-service.json` asserts it.

### 1c — yield queries and the ocs acceptance tests

Ships: `NativeSql.ql` (retires `RawQueries.ql`), `JakartaMigration.ql`,
`HibernateTypes.ql`, `OpenApiSurface.ql`, `ApiSurface.ql`, `Configuration.ql`,
`ErrorHandling.ql`, plus `join_openapi.py`.

**Exit criteria.** `NativeSql.ql` ≳250 SQL-bearing sites vs the previous 198.
`JakartaMigration.ql` ~297 pending rows, ~286 of them `javax.persistence`.
`HibernateTypes.ql` ~31 annotation sites plus the `com.vladmihalcea` references.
`OpenApiSurface.ql` ~148 `swagger2` and ~1012 `openapi3` rows. `join_openapi.py`
residual small, every unmatched row individually explained.

### Landing mode — resolve before 1c

`rule_coverage.py` computes the CI denominator from pack rule_ids plus ast-grep
over `scripts/fixtures/spring_signals/`. Deleting `RawQueries.ql` and renaming
rule_ids fails CI unless fixtures and baseline move in the same PR. Two options,
pick one and write it down:

- **A — external.** Wave 1 lives under `codeql/packs/` with the ocs harness
  outside the coverage denominator until a vocabulary-sync PR. Ships fastest,
  leaves the pack uncovered by CI in the interim.
- **B — in-tree with coordinated migration.** Land alongside ast-grep rule,
  fixture and baseline updates driven by `docs/RULE_ID_MIGRATION.md`. Larger PR,
  keeps CI honest throughout.

Recommendation: **A for 1a/1b, B for 1c.** 1a and 1b add no rule_ids and remove
none, so they cannot move the denominator; 1c is where `RawQueries` dies and
fourteen rule_ids appear, so that is the PR that should carry the vocabulary
migration.

### Regression found in review — fail-closed is not free

Closing `metaResolutionEnabled()` made `isOrMeta(a, "...stereotype", "Controller")`
degrade to an exact match on `@Controller`, dropping all 48 `@RestController`
classes in ocs-api-service from `api_surface__controller`. The pack being
replaced enumerated both explicitly and had no such hole. The switch traded a
verified capability for an unverified one and called it caution.

**Rule going forward: a fail-closed switch is only safe when the closed state is
at least as capable as the baseline it replaces.** Otherwise it is a recall
regression wearing a safety label — and worse than an unguarded feature, because
it looks deliberate.

Fix: `Catalog.qll::metaEdge` hardcodes Spring's *documented* meta-annotation
graph (stereotypes onto `@Component`, `@RestController` onto `@Controller`,
mapping shortcuts onto `@RequestMapping`, `@SpringBootApplication` onto
`@Configuration`, advice, exchange shortcuts). That is a published API contract,
not an extractor inference, so it needs no probe. `metaReaches` is its
reflexive-transitive closure and is always available. The gated transitive
predicate now buys exactly one thing the table cannot: project-local composed
annotations — a set that is empty in ocs-api-service.

This was the wave 4 fallback. The regression proves it belongs in wave 1.

**Add to 1b exit criteria:** `api_surface__controller` returns 49 rows (48
`@RestController` + 1 `@Controller`) with the switch closed.

### Trust gate — meta-annotation resolution

`metaResolutionEnabled()` is `none()` and stays that way until
`harness/probe-meta-annotations.ql` passes on a real database. While it is
closed:

- No wave 1 exit criterion depends on meta-resolution. Check the list above —
  none do.
- **Do not claim the 48 `@RestController` recovery, or the
  `@SpringBootApplication` stereotype recovery.** Those are wave 4 deliverables.
  Quoting them from a closed switch would put exact-match numbers into a
  dashboard labelled as meta-resolved recall.
- Note what the probe will likely show for ocs specifically:
  `first_party_annotation_types = 0`. This repo declares no `@interface` at all,
  so first-party composed annotations are not the motivation here — library
  meta-annotation extraction is the whole question.

## Wave 2 — schema migration + coverage for the remaining four queries

`References.ql`, `Security.ql`, `Observability.ql`, `Testing.ql` are carried into
wave 1 **unmodified**, still emitting the legacy 3-column schema, with banner
comments recording their known gaps. The harness excludes them deliberately.

- `References.ql` → meta-annotation stereotypes (recovers 48 `@RestController` +
  `@SpringBootApplication`), plus *implicit* beans: ~44 Spring Data repositories
  carry no stereotype at all, so no annotation rule can find them. Emit the
  imported FQN, which the current version drops.
- `Testing.ql` → split JUnit 4 from Jupiter (174 vs 1 file here — that split *is*
  the vintage-removal burndown), add the Boot test slices, add
  `@MockBean`→`@MockitoBean` as a generation-tagged pair.
- `Security.ql`, `Observability.ql` → convert to explicit absence assertions.
  Add `WebSecurityConfigurerAdapter` and `@EnableGlobalMethodSecurity` (still
  present-but-deprecated through Spring Security 7.1) so the queries stay useful
  on sibling services that do use Spring Security.
- New `Logging.ql` for the actual observability surface here: 34 slf4j logger
  declarations and 48 `@LogAccess` sites from `eols-commons-logging`.

## Wave 3 — the remaining ocs-ranked queries

- `Caching.ql` — 29 `@Cacheable(cacheNames = "ocs-api-service")` (a single cache
  name for everything, worth flagging on its own), `RedisTemplate<String,String>`
  (the erasure fix from wave 1 is what makes this detectable),
  `JedisConnectionFactory`, direct `redis.clients.jedis` use,
  `GenericJackson2JsonRedisSerializer` as a Jackson-3 coupling point.
- `BeanWiring.ql` — 186 field `@Autowired` vs 18 constructor; `@EnableAsync` +
  `@Async(constant)`; `@ComponentScan` of external packages, which is why
  `ErrorHandling.ql` returns zero in-repo.
- `Jackson.ql` — generation-tagged `com.fasterxml.jackson` (Jackson 2) vs
  `tools.jackson` (Jackson 3). Note the exception: `jackson-annotations` keeps
  the `com.fasterxml.jackson.annotation` package in Jackson 3, so a naive
  package-prefix rule mis-tags 743 annotation sites here.

## Wave 4 — architectural work deferred from P1

- **Verify the meta-annotation traversal** against a built database. Everything
  in `Annotations.qll` assumes CodeQL extracts annotations sitting on *library*
  annotation types. Probe first; if it does not hold, hardcode Spring's own
  chains and reserve the transitive predicate for first-party composed
  annotations.
- **TYPE_USE probe.** JSpecify `@Nullable` attaches to the type reference, not
  the declaration, so `Annotatable.getAnAnnotation()` will not see it. Inert on
  Boot 2.7; mandatory by Boot 4.
- **Import vs type-usage double counting.** Decide whether the oracle counts
  sites or files, and make every query consistent. ast-grep rules will count
  sites.
- **`semmle.code.java.frameworks.spring.*` experiment.** Run the shipped
  `SpringComponent`/`SpringController` classes against the hand-rolled catalog on
  the same database. The delta is a publishable result for the bytecode-oracle
  writeup, and if the library wins, delete catalog tuples.
- **Non-Java sources.** 14 yml files carrying ~350 config keys, plus
  `bootstrap.yml` profiles, are invisible to every query here. `codeql/xml` is
  already a transitive dependency; `.yml`/`.properties` extraction needs
  confirming separately.

## Wave 5 — generalisation

- Migrate `Catalog.qll` to a data extension / model pack once it exceeds ~200
  tuples or a non-QL author needs to edit it.
- Second-framework proof: add Micronaut or Quarkus tuples plus a sibling query
  pack, changing nothing in `java-signals-lib`. If that requires library edits,
  the abstraction is wrong and should be fixed then, not now.
- Second-language proof: `python-signals-lib` emitting the identical eleven
  columns. This is the real test of the schema decision made in wave 1.
- Emit the same schema from ast-grep and semgrep rule sets so the three-way
  comparison joins on `(file, symbol, rule_id)` rather than `(file, line)`.

---

## Dual schema during waves 1-2 — the tax, priced

`References/Security/Observability/Testing` stay on the legacy 3-column shape
through wave 1 while everything else emits v1. That is honest only if it is also
*declared*, so every v1 row carries `schema_version = "v1"` and the decoder
branches on it rather than inferring shape from column count. Inferring arity is
how a schema migration becomes a silent mis-parse.

The tax is real and lands on `_scanner_codeql.py`, the covering/recall joins, and
anything else assuming one BQRS shape. Budget an explicit decoder branch. If that
branch is not in the same release train as 1c, then wave 1 campaign output is
**harness-only** until wave 2 migrates the remaining four queries — say which,
do not leave it implicit.

## Queue labelling

This is **parallel oracle-arm work**. It is not a substitute for, and does not
supersede, mid-size Stage-4 or the lineage dialect entries. Label it as a
separate arm so "next engineering" does not thrash between them. Waves 2-5 are
individual queue entries; wave 4 is the trust gate that must clear before any
meta-annotation-derived number is quoted anywhere.

## Measurement notes carried into every wave

1. **Join on `(file, symbol, rule_id)`, not `(file, line)`.** Annotations inline
   with declarations and multi-line concatenations make line agreement noisy.
2. **Reconcile the extracted-file set before computing precision/recall.** CodeQL
   sees only what the build compiled. `create-db.sh` prints the delta.
3. **`@kind table` does not produce SARIF.** These are raw result tables; they go
   through `query run` + `bqrs decode`.
4. **Precompile before timing.** `compiled: false` puts QL compilation inside
   every measurement, which is most of the CodeQL-vs-ast-grep latency delta.
5. **A zero-row query is not self-evidently correct.** The expectations spec
   makes asserted-zero distinguishable from broken, and a missing CSV is an
   error rather than a zero.
6. **Check for duplicate rows** (`count(*)` vs `count(distinct …)`) before
   quoting any total. Annotated generic types can yield one row per
   instantiation.
