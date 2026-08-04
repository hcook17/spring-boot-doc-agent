# CodeQL spring-signals Wave 1 (P0) — falsifiers and local reproduction

**Date:** 2026-08-04  
**Scope:** Pack correctness only. CodeQL CLI remains intentionally absent from CI
(CONSTRAINTS Runtime 4). Fixture non-vacuity continues to run via
`filesystem`+`ast-grep` sharing the pack `rule_id` vocabulary.

## Product contract

Semantic inventory rows: `(file, line, rule_id[, attrs])`. Migration
generation tags are deferred to campaign Wave 4 (`SpringSignatures.qll`
overlay). Shared libraries under `codeql/spring-signals/lib/` are the
expansion seam for multi-framework packs.

## P0 falsifiers (what Wave 1 closed)

| Id | Defect | Fix shape |
|----|--------|-----------|
| P0.1 | `ParameterizedType` / interface injection invisible to exact FQN | `erasureOrSourceSupertypeHasName` in `TypeMatchers.qll`; Messaging + OutboundClients |
| P0.2 | `@Table(schema=…)` / bare `@Table` dropped entity rows | total `getTableName` — unnamed `@Table` → `""`, not no-row |
| P0.3 | Direct `getASupertype()` miss on intermediate repo bases | `getASourceSupertype+()` + entity arg from parameterized ancestor |
| P0.4 | `StringLiteral` / `BooleanLiteral` only | `CompileTimeConstantExpr` / static-final boolean for table name + `nativeQuery` |
| P0.5 | `concat … order by line` nondeterministic on same-line literals | order by `(startLine, startColumn)` |
| P0.6 | Collapsed `rule_id`s | `configuration__value`; `error_handling__rest_advice` / `__exception_handler` |
| P0.7 | Class vs method mappings conflated; no path/method | `api_surface__class_mapping` / `__method_mapping` + `path`/`http_method` columns |
| P0.8 | `bindingset` + `.*\\.java$` | shared `isJavaSource` → `^src/(main\|test)/java/.*\\.java$` |

## Fixture guards (ast-grep path)

- `KafkaTemplate<String,String>` + `KafkaOperations` + `RedisTemplate<String,String>`
- `SchemaOnlyTableEntity` with `@Table(schema = "ehe")`
- `BaseBillingRepository` / `TaggedBillingRepository` (transitive; CodeQL-only for the tagged leaf)
- Same-line `@Query` concat; `nativeQuery = QueryConstants.NATIVE` (Python/ast-grep still labels the latter JPQL — intentional dual-engine delta until a shared constant resolver exists)

## Local CodeQL reproduction (when CLI is installed)

```bash
# From a traced DB of the Stage-0 fixture or a target repo:
codeql query run codeql/spring-signals/Messaging.ql --database "$DB" --output /tmp/messaging.bqrs
codeql bqrs decode /tmp/messaging.bqrs --format=csv

codeql query run codeql/spring-signals/Persistence.ql --database "$DB" --output /tmp/persistence.bqrs
codeql bqrs decode /tmp/persistence.bqrs --format=csv

codeql query run codeql/spring-signals/RawQueries.ql --database "$DB" --output /tmp/raw.bqrs
codeql bqrs decode /tmp/raw.bqrs --format=csv
```

Acceptance on an ocs-scale DB (follow-up live run, not CI): transitive repos
appear; `KafkaTemplate`/`RedisTemplate` parameterized fields appear; schema-only
`@Table` entities emit; constant `nativeQuery` stays `native`; same-line concat
stable.

## Deferred (Waves 2–4)

Meta-annotations, repeatables, `source_set` column, TYPE_USE, ocs-ranked new
queries, `SpringSignatures.qll` generation overlay, pack `defaultSuiteFile`.
