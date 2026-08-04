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

### Wave 0 item: layering — closed, and wider than the review comment

`Annotations.qll` no longer imports Spring facts. But satisfying that criterion
alone would have left the property it protects still false: `Catalog.qll` is
dense with framework namespace literals, and it lived in the pack documented as
framework-agnostic. A Micronaut or Quarkus pack depending on `java-signals-lib`
would have inherited all of them.

**No count is quoted here on purpose.** Successive drafts of this rationale
carried different figures, each hand-derived from an unpinned grep and each
load-bearing in an argument. Another hand-count would be the same defect with a
new value, so the measurement moved into `harness/check-invariants.py`, which
pins both patterns in code and prints the figures.

Removing the numbers from prose was not enough on its own: a later draft quoted
the script's own output back into the docs and into the script's docstring, and
an unrelated *comment* edit then moved the comment-inclusive figure and made all
three stale. Two rules came out of that, and check 6 enforces the second:

- The comment-inclusive figure is not an invariant. It changes whenever anyone
  edits prose. Only the code-only figure carries meaning, and it should still be
  read from output rather than copied.
- Cite the script; never hardcode. An unenforced convention decayed within two
  edits, so the check now fails on any count claim in a doc or QL comment.

Fixing the letter of a review comment while the invariant it guards stays broken
is worth naming as its own failure mode — it converts a real defect into a
closed ticket.

**Verification predicate — measured, not an import-line grep.** "Does
`Annotations.qll` import Catalog" is the wrong test; it was satisfiable while the
property stayed false. The test is:

1. framework string literals in `java-signals-lib/**` code (comments excluded) = 0
2. `Catalog.qll` is not in `java-signals-lib`
3. `declaredMetaEdge` has at least one contributor in the query pack's import
   closure

Checks 1-3 (plus the `or`-`or` lint) are implemented in
`harness/check-invariants.py` and run without a CodeQL CLI. It discovers the pack
root by searching rather than by path arithmetic, and accepts `--root`, so a copy
mirrored into a review overlay still works.

That last point is not incidental. This project has now produced three checkers
that failed for environmental reasons unrelated to what they check: `Probe.ql`
could not resolve pack imports while it lived in `harness/`; `run.sh` aborted on
a comment line before its first assertion; `check-invariants.py` died on a
hardcoded relative root when mirrored. **A checker that dies during its own setup
reports nothing, and reporting nothing looks like passing unless the exit code is
read carefully.** Verification machinery deserves the same adversarial reading as
the code it verifies -- arguably more, because nothing downstream is checking
*it*. Wave 0 item 1 is
green when that script exits 0. The script is also the source for every
framework-reference figure in this document.

(3) cannot be checked statically. No subclass in the closure ⇒
`declaredMetaReaches` is empty ⇒ `isOrMeta` degrades to exact-only ⇒ the
`@RestController` regression reopens, **with no compile error**. The import
comment in `_Common.qll` is a mitigation, not a proof; `Probe.ql`'s
`closed_state_restcontroller_is_controller` > 0 is the only proof, and it is
still unrun.

Final layering:

| Pack | Contents | Framework references |
|---|---|---|
| `java-signals-lib` | `Schema.qll` (row shape), `Types.qll` (generic-safe matching), `Annotations.qll` (meta resolution + `MetaAnnotationEdges` extension point) | none outside doc comments |
| `spring-signals` | `Catalog.qll`, `SpringMetaEdges.qll`, `_Common.qll`, 10 v1 queries, `Probe.ql` | all of them |

The library declares the *shape* of a meta-annotation graph; each framework pack
contributes its own edges by extending `MetaAnnotationEdges`. `Probe.ql` moved
from `harness/` into the pack, because a `.ql` outside a pack directory cannot
resolve pack imports and would not have seen the Spring contribution — an
abstract class only takes effect where a subclass is in the import closure.

New compile risks this introduces, for the wave 0 list:
`codeql.util.Unit` (new direct dependency `codeql/util: ^2.0.40` on the library
pack), and abstract-class contribution across a pack boundary.

### 1a-pre ("wave 0") — make it run once

Nothing in this pack has ever executed. Two compile errors (`Catalog.qll`
unbound variables; `NativeSql.ql` referencing a nonexistent `Argument` class)
meant `codeql query compile` could not have passed, and `run.sh` aborted on the
first comment line in `expected-empty.txt` before reporting any assertion.

Every number in this document is grep-derived. Wave 0 is: fix the compile
errors, run `create-db.sh` and `run.sh` once against ocs @ develop, and let the
observed counts falsify the exit criteria before anyone debates encoding formats.
The repository fan-out and the Jakarta denominator were both caught by reading;
assume more are not.

### 1a — compile the foundation

Ships: `codeql-workspace.yml`, `java-signals-lib` (`Schema.qll`, `Types.qll`,
thin `Catalog.qll`), `_Common.qll`, and `Persistence.ql` only.

`Annotations.qll` ships in-tree but **disabled**: `metaResolutionEnabled()` is
defined as `none()`, which disables only the *discovered* half of meta
resolution. Spring's documented meta-annotation graph in `SpringMetaEdges.qll`
is hardcoded and always on, so the closed state is exact match PLUS that graph --
not exact-only. See "trust gate" below.

**Exit criteria — this is a merge blocker, not a footnote.**

- `codeql query compile` green against pinned `codeql/java-all` 9.2.x.
- `create-db.sh` green on `ocs-api-service @ develop`, extraction delta 0.
- **Found in review, already fixed:** deleting the unbound `vladmihalcea`
    branch from `signature` left `or / comment / or` — an empty disjunct, itself
    a compile error. Removing a disjunct means removing one of its adjacent
    separators; a comment does not occupy the slot. The scan is now shipped as
    check 1 of `harness/check-invariants.py`. It strips comments AND string
    literals before tokenising: a raw `or\s*//.*\n\s*or` regex false-positives
    on the ~20 legitimate `or` + explanatory-comment forms in this pack, and a
    comment-only strip still trips over `or` inside a regex literal.
- `codeql.util.Unit` (new direct dependency) and abstract-class contribution
    across a pack boundary.
- The construct risk list is cleared, not deferred: `getASourceSupertype*()`
  and `getSourceDeclaration()` arities; `regexpCapture` group semantics in
  `sourceSetOf`; `MethodCall` vs `MethodAccess` naming; `TypeLiteral.getTypeName()`;
  and the `concat`-over-empty-returns-`""` idiom that makes `attr()` total.
- `Probe.ql` runs and its output is recorded, whether or not
  the switch is flipped. Two of its checks are hard gates independent of the
  switch:
  - `closed_state_restcontroller_is_controller` > 0 — proves the contributed edges close
    the recall regression without reopening the switch.
  - `ambiguous_symbols` = 0 — proves `symbolOf` is single-valued, so `sym`'s
    `min()` is picking from a set of one rather than choosing arbitrarily.
  - `unresolved_symbols` = 0 and `annotations_with_symbol` = `annotations_total`
    — proves `symbolOf` is **total**. This is the sharper of the two gates:
    `sym` appears in every `select`, so a missing symbol deletes the row rather
    than blanking a column. Found during 1a prep: the first `symbolOf` resolved
    annotations only when the annotated element was a `RefType`, and imports not
    at all, which would have silently dropped most annotation rows and all ~297
    JakartaMigration import rows. Same failure mode already called out for
    `attr()` and `tableNameOf` — reproduced in the helper that guards every
    query. `symbolOf` now has a file-path tier that cannot fail.

### 1b — P0 on the new types

Ships: `Persistence.ql`, `Messaging.ql`, `OutboundClients.ql` on the v1 schema.
Supersedes #88's P0 work.

**Exit criteria.** `persistence__repository` reports exactly one row per
repository interface per *most specific* root — the four `BookBased*Repository`
types that the one-hop supertype walk missed appear once each, not five times
each. `persistence__repository_marker` reports four rows for `BookBasedRepository`.
`Messaging.ql` returns 0 and `expected-empty.txt` asserts it.

The "once each" clause is load-bearing: the naive any-reachable-root form fanned
out ~5x, which would have made this test report 12-20 and fail for a reason
unrelated to the transitive-supertype fix it exists to verify.

### 1c — yield queries and the ocs acceptance tests

Ships: `NativeSql.ql` (retires `RawQueries.ql`), `JakartaMigration.ql`,
`HibernateTypes.ql`, `OpenApiSurface.ql`, `ApiSurface.ql`, `Configuration.ql`,
`ErrorHandling.ql`, plus `join_openapi.py`.

**Exit criteria — each names its denominator.** An earlier draft quoted totals
without saying which `rule_id` they counted, and two of them were unsatisfiable:
`JakartaMigration` emits import, annotation AND type rows per finding, so "~297
pending rows" was really ~600+ unless filtered to imports. A criterion that
cannot pass is worse than no criterion — it gets relaxed on first contact rather
than investigated.

| Query | Filter | Expected |
|---|---|---|
| `NativeSql` | `rule_id LIKE 'sql__%'` | ≳250 (was 198 under `RawQueries`) |
| `NativeSql` | `rule_id = 'sql__data_query_native'` | ~197 |
| `JakartaMigration` | `rule_id = 'jakarta__pending_import'` | ~297 |
| `JakartaMigration` | `rule_id = 'jakarta__pending_import' AND signal LIKE 'javax.persistence%'` | ~286 |
| `HibernateTypes` | `rule_id LIKE 'hibernate__%' AND rule_id NOT LIKE '%legacy_types%'` | ~31 |
| `OpenApiSurface` | `generation = 'swagger2'` | ~148 |
| `OpenApiSurface` | `generation = 'openapi3'` | ~1012 |
| `join_openapi.py` | — | residual small, every unmatched row explained |

`hibernate__legacy_types_*` is excluded from the 31 because it counts
*references* to `com.vladmihalcea` types, not sites needing change — a class
referenced three times in a file yields three rows plus an import row. Useful as
a locator, wrong as a burndown denominator. Same caveat applies to any
import-plus-usage rule pair; see wave 4.

All counts are grep-derived PREDICTIONS, not observations. Wave 0 exists to
falsify them.

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

Fix: `SpringMetaEdges.qll` hardcodes Spring's *documented* meta-annotation
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

### Audit — every `isOrMeta` call site

Promised after the regression, done. The check is not "does the doc say meta is
optional" but "is the closed state at least as capable as the pack this
replaces", evaluated per call site.

| Query | Target | Closed-state coverage | Verdict |
|---|---|---|---|
| `ApiSurface` | `stereotype.Controller` | contributed edge `RestController` → `Controller` | OK — was the regression |
| `ErrorHandling` | `ControllerAdvice` | explicit second arm **and** contributed edge `RestControllerAdvice` → `ControllerAdvice` | OK, belt and braces |
| `ErrorHandling` | `RestControllerAdvice` | exact; no Spring meta-subtypes | OK |
| `Configuration` | `ConfigurationProperties` | exact; no Spring meta-subtypes | OK |
| `NativeSql` | `data.jpa.repository.Query` | exact; no Spring meta-subtypes | OK |
| `NativeSql` | `data.jpa.repository.NativeQuery` | exact; no Spring meta-subtypes | OK |

The general rule this audit encodes: **`isOrMeta` is only safe for a target that
some annotation reaches *exclusively* via meta if `SpringMetaEdges` carries that edge.**
Adding an `isOrMeta` call for a new target requires either an exact-match
alternative or a `SpringMetaEdges` entry in the same change.

The `ControllerAdvice` row is a disjunction inside one `exists`, so a
`@RestControllerAdvice` satisfying both arms still yields one row, not two.

### Trust gate — meta-annotation resolution

`metaResolutionEnabled()` is `none()` and stays that way until
`codeql/packs/spring-signals/Probe.ql` passes on a real database. While it is
closed:

- No wave 1 exit criterion depends on meta-resolution. Check the list above —
  none do.
- **The 48 `@RestController` and the `@SpringBootApplication` stereotype
  recoveries MAY be claimed in wave 1.** Both edges are contributed by `SpringMetaEdges.qll`,
  which is a published Spring API contract, not an extractor inference. An
  earlier draft of this section said the opposite; that text predated the
  `SpringMetaEdges` fix and understated the closed state. A safety label that
  understates capability is not conservative — it trains readers to discount
  numbers that are in fact contract-backed, which is how a correct result gets
  thrown away.
- **What must NOT be claimed while the switch is closed** is recall over meta
  edges *not* in the table: project-local composed stereotypes and uncatalogued
  third-party annotations. That is what the probe gates.
- Note what the probe will likely show for ocs specifically:
  `first_party_annotation_types = 0`. This repo declares no `@interface` at all,
  so first-party composed annotations are not the motivation here — library
  meta-annotation extraction is the whole question.

## Wave 2 — schema migration + coverage for the remaining four queries

`References.ql`, `Security.ql`, `Observability.ql`, `Testing.ql` are carried into
wave 1 **unmodified**, still emitting the legacy 3-column schema, with banner
comments recording their known gaps. The harness excludes them deliberately.

- `References.ql` → route stereotypes through `isOrMeta` so it picks up the
  contributed meta graph (recovers 48 `@RestController` + `@SpringBootApplication`
  with the switch still closed), plus *implicit* beans: ~44 Spring Data repositories
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
5. **A zero-row query is not self-evidently correct.** `expected-empty.txt` makes
   asserted-zero distinguishable from broken.
6. **Check for duplicate rows** (`count(*)` vs `count(distinct …)`) before
   quoting any total. Annotated generic types can yield one row per
   instantiation.
