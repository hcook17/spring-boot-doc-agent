# spring-signals

Semantic signal extraction for JVM services, structured as a language-scoped
CodeQL library pack plus per-framework query packs. Wave 1 targets
`ocs-api-service` (Spring Boot 2.7.18, Java 17, `javax.*`).

    codeql/
      codeql-workspace.yml
      packs/
        java-signals-lib/          library pack -- language only, no framework facts
          signals/Schema.qll       11-column row schema + source-set filtering
          signals/Types.qll        generic-safe, transitive type matching
          signals/Annotations.qll  meta resolution + MetaAnnotationEdges hook
        spring-signals/            query pack -- all framework knowledge
          Catalog.qll              (framework, pkg, name, kind, generation) facts
          SpringMetaEdges.qll      Spring's documented meta graph, contributed
          Common.qll
          Probe.ql                 trust gates; excluded from the suite
          *.ql
    harness/
      check-invariants.py          static gates; runs without a CodeQL CLI
      create-db.sh                 matches the -Werror / Error Prone toolchain
      run.sh                       precompile, run wave 1, decode CSV, assert
      expected-empty.txt           asserted zero-result queries
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

Static invariants first — no CodeQL CLI required, and the source of every
framework-reference figure quoted in the docs:

    python3 harness/check-invariants.py

It locates the pack by searching for `codeql/packs/java-signals-lib`, so it runs
from `harness/`, from the pack root, from an unrelated working directory, or
from a review overlay where a copy of the script sits beside an extracted
`spring-signals/`. If none of those apply, pass the root explicitly:

    python3 check-invariants.py --root path/to/spring-signals

An earlier version computed its root as `__file__/../..`, which meant a copy
mirrored to the top of a review archive died with a bare `FileNotFoundError`
from inside check 2 — an error describing neither the real problem nor the fix.

Then the parts that need a toolchain:

    export artifactory_user=... artifactory_password=...
    ./harness/create-db.sh
    ./harness/run.sh
    python3 harness/join_openapi.py \
      --api-surface out/ApiSurface.csv \
      --openapi src/docs/api/OASv3/ocs-api-service.yaml

## Status: NOT YET COMPILED — this is a merge blocker

`codeql query compile` green and `create-db.sh` green on ocs @ develop are exit
criteria for wave 1a, not follow-ups. Until both pass this is a design drop.

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

Meta-annotation resolution ships in two halves.

**Documented half — always on.** `SpringMetaEdges.qll` hardcodes Spring's
published meta-annotation graph (`@RestController` → `@Controller`,
`@SpringBootApplication` → `@Configuration`, mapping shortcuts →
`@RequestMapping`, and so on). Contract-backed, no probe needed, claimable in
wave 1. This is what keeps the closed state from being a recall regression
against the pack it replaces.

**Discovered half — gated.** `metaResolutionEnabled()` is `none()`, disabling the
transitive walk over extracted annotation metadata. That walk depends on CodeQL
extracting annotations on *library* annotation types, which is unverified. Run
`codeql/packs/spring-signals/Probe.ql` and record its output before flipping it.

So the closed state is exact match ∪ the contributed edges, not exact-only. Recall over
meta edges outside the table — project-local composed stereotypes, uncatalogued
third-party annotations — is the only thing that must wait for the probe.
