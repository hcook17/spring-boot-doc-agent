# spring-signals

Semantic signal extraction for JVM services, structured as a language-scoped
CodeQL library pack plus per-framework query packs. Wave 1 targets
`ocs-api-service` (Spring Boot 2.7.18, Java 17, `javax.*`).

    codeql/
      codeql-workspace.yml
      packs/
        java-signals-lib/          library pack, framework-agnostic
          signals/Schema.qll       11-column row schema + source-set filtering
          signals/Annotations.qll  meta-annotation + repeatable resolution
          signals/Types.qll        generic-safe, transitive type matching
          signals/Catalog.qll      (framework, pkg, name, kind, generation) facts
        spring-signals/            query pack
          _Common.qll
          *.ql
    harness/
      create-db.sh                 matches the -Werror / Error Prone toolchain
      run.sh                       precompile, run wave 1, decode CSV, assert
      check_assertions.py          fail-closed JSON assertion engine
      expectations/                asserted/minimums/snapshot/rule_minimums specs
      join_openapi.py              join against the generated OpenAPI contract
    docs/
      CAMPAIGN.md                  architectural decision + waves 1-5

## Row schema

Every wave-1 query emits the same eleven columns. This schema, not the QL, is the
contract that a future ast-grep rule set or `python-signals-lib` implements.

    file, start_line, end_line, source_set, schema_version,
    rule_id, framework, generation, symbol, signal, detail

`NativeSql.ql` appends two SQL-specific columns (`schema_refs`, `uses_json`).

`symbol` is the join key and is ALWAYS `Schema.qll::symbolOf`; `signal` is what
was detected (annotation FQN, type FQN, property key). They were one column in
the first draft, which is how `Persistence.ql` came to emit a class name in one
branch and `javax.persistence.Column` in another. See docs/SYMBOLS.md.

`schema_version` exists because waves 1-2 ship two row shapes in one pack.
Decoders branch on it; they must not infer shape from column count.

`generation` is populated only where it drives a burndown metric. Blank means
*not tracked on a version axis*, never *unknown*.

## Run

    export artifactory_user=... artifactory_password=...
    ./harness/create-db.sh
    ./harness/run.sh
    python3 harness/join_openapi.py \
      --api-surface out/ApiSurface.csv \
      --openapi src/docs/api/OASv3/ocs-api-service.yaml

## Status: NOT YET COMPILED — this is a merge blocker

`codeql query compile` green and `create-db.sh` green on ocs @ develop are exit
criteria for wave 1a, not follow-ups. Until both pass this is a design drop.

The gate now exists: `.github/workflows/spring-signals.yml` compiles both packs,
enforces committed `codeql-pack.lock.yml` files, builds the jar-based fixture
(`harness/fixture-repo/`), and runs wave 1 against it with
`harness/expectations/fixture-repo.json` as the assertion spec. The ocs
expectations (`harness/expectations/ocs-api-service.json`) were verified
structurally against the ocs checkout on 2026-08-05; the ocs database run
itself still needs the CLI plus Artifactory credentials, which CI does not
have. First green fixture run flips this section, not before.

None of this QL has been run through `codeql query compile`. It was written
against the CodeQL Java standard library without a CLI available, so treat the
first compile as part of the review, not as a formality. The constructs most
likely to need adjustment, in rough order of risk:

- `getASourceSupertype*()` and `getSourceDeclaration()` arities in
  `Types.qll` — these are the load-bearing replacements for the P0 defects.
- `regexpCapture` group semantics in `Schema.qll::sourceSetOf`.
- `getReceiverType()` on `MethodCall` in `NativeSql.ql` (older library versions
  name this class `MethodAccess`).
- `TypeLiteral.getTypeName()` in `ErrorHandling.ql`.
- The `concat`-over-empty-set-returns-`""` idiom used throughout `attr()`, which
  is what makes the optional-attribute helpers total.

Meta-annotation resolution ships **disabled**. `metaResolutionEnabled()` is
defined as `none()`, so `isOrMeta` degrades to exact matching and no wave 1
number depends on the unverified extractor assumption. Run
`harness/probe-meta-annotations.ql` and record its output before flipping it.
Until then, do not quote the 48 `@RestController` recovery — that is a wave 4
deliverable.
