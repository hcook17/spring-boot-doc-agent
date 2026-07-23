# Documentation taxonomy

One entry per output file. For each: what it's for, which evidence sources feed it, and — critically — what's safe to infer from code versus what genuinely needs a clarifying question. Getting that boundary wrong is the main failure mode of this whole pipeline: guessing at things like "known limitations" or "who owns this table" produces confident-sounding fiction. When evidence is thin, the doc-writer should write "not evidenced in code; not answered in interview" rather than fill the gap with a plausible guess.

Evidence sources referenced below:
- **signals** = `spring_signals.json` (deterministic AST scan via ast-grep — see `scripts/spring_signal_scan.py`)
- **summaries** = the merged output of Stage 1 (`file-summarizer` subagents)
- **arch** = the merged Mermaid diagram from Stage 3 (`architect-merge`)
- **interview** = answers collected by the orchestrator directly from the user in Stage 4

## What counts as "code evidence"

Not everything that's technically text in the repository carries the same evidentiary weight, and a doc-writer subagent that isn't told the difference can accidentally launder a lower-confidence source into an `[Evidenced — ...]` tag it hasn't actually earned. Four boundary cases worth being explicit about:

- **CI configuration** (GitHub Actions workflows, Jenkinsfiles, and similar) counts as code evidence, same as any other checked-in config — it's config-as-code, not prose about code. Cite it the same way you'd cite a Dockerfile.
- **Generated artifacts** (anything under an excluded build-output directory, generated OpenAPI clients, Lombok-expanded accessors, and the like) do **not** count as code evidence in their own right — they're not checked in, not stable across builds, and not what a reader should be pointed at. If something about codegen is worth stating, cite the *thing that configures the generator* (the annotation, the OpenAPI spec file, the Gradle plugin block), not the generated output itself.
- **Comments and docstrings** do count as code evidence, but they're a weaker kind than an annotation or config value the scanner mechanically extracted — a comment can be stale or simply wrong in a way `@PreAuthorize("hasRole('ADMIN')")` structurally can't. Quote the comment directly rather than paraphrasing it, so a reader can judge its age and confidence for themselves. `known_limitations.md`'s existing rule — TODO/FIXME comments are "candidates, not facts" — is the right posture generalized to comments everywhere, not just TODOs.
- **Pre-existing documentation already in the repo** (an existing README, a `docs/` folder that predates this pipeline, an architecture wiki page someone pasted in) is explicitly **not** the same thing as code evidence, no matter how confidently it's written — it's a claim a person made at some point, unverified against the code as it stands today. Tag anything sourced this way `[Per existing docs — path, unverified against code]` rather than `[Evidenced — ...]`. `architect-merge`'s discrepancy section already does exactly this cross-check for architecture.md specifically; this rule generalizes the same caution to any of the other thirteen files that happens to draw on pre-existing repo docs.

---

## 1. readme.md
**Purpose**: front-door orientation — what this service is, why it exists, how it fits into the broader system.
**Evidence**: summaries (dominant business capability, entry points), arch (one-paragraph narrative), signals.api_surface (what this service exposes).
**Interview-worthy**: the service's role in the broader system if it's not derivable from code alone (e.g. "is this the system of record for invoices, or a read replica view?"). Ask once, reuse the answer across every other doc that needs it.

## 2. architecture.md
**Purpose**: the merged Mermaid diagram plus prose explaining major subgraphs/modules.
**Evidence**: arch (diagram + discrepancy notes), summaries (`group_function` fields).
**Interview-worthy**: nothing new — this is almost entirely code-derived. If `architect-merge`'s discrepancy section flagged a conflict with an existing README/doc, surface it here rather than silently picking a side.

## 3. integrations.md
**Purpose**: every external system this service talks to — other services, message brokers, third-party APIs.
**Evidence**: signals.outbound_clients (RestTemplate/WebClient/FeignClient), signals.messaging (Kafka/RabbitMQ/JMS listeners and producers), signals.api_surface (this service's own exposed endpoints, for the "who calls us" half).
**Interview-worthy**: **who calls this service's endpoints** — that's almost never derivable from the codebase itself (it lives in the caller's code, an API gateway config, or someone's head). Ask explicitly: "Which other services or teams consume the endpoints in `<api_surface list>`?" Also ask about any external (non-code, e.g. SFTP drop, shared DB) integrations static analysis can't see.

## 4. authorization.md
**Purpose**: what's protected, how, and by which roles/scopes.
**Evidence**: signals.security (`@PreAuthorize`/`@Secured`/`SecurityFilterChain`/etc. — the matched line, truncated to 200 characters; there's no dedicated role/scope field, but the role/scope string is usually visible inline within that matched line for single-line annotations).
**Interview-worthy**: whether the roles found in code (e.g. `BILLING_READ`) map to a real role catalog elsewhere (an IdP, an internal permissions doc), and whether any endpoint's *absence* from the security evidence is intentional (unsecured by design) versus a gap. Flag every `@RestController`-mapped endpoint with **no** matching security annotation as a candidate question rather than assuming either "intentionally public" or "bug."

## 5. database.md
**Purpose**: tables this service owns or touches, and which code paths read vs. write them.
**Evidence**: signals.persistence (entities, table names via `entity_table_map`, repository interfaces), signals.raw_queries (tagged `jpql` vs `native` — see note below).
**On JPQL vs native SQL**: `@Query` values that are JPQL reference **entity names**, not table names — resolve them through `entity_table_map` before treating them as table references. Native queries (`nativeQuery = true`) contain real SQL and can be handed to a real SQL parser (e.g. SQLLineage) for source/target table extraction if you want that level of rigor; JPQL generally can't be, reliably — HQL/JPQL parsing is a known gap in general-purpose SQL lineage tools (SQLLineage itself has an open issue about missing source tables on HQL input). Spring Data **derived query methods** (e.g. `findByStatus(String status)` with no `@Query` at all) produce no SQL text whatsoever to inspect — infer their target table from the repository's generic type parameter instead.
**Interview-worthy**: **write ownership** — which team/service is the authoritative writer for a table this service only reads, or vice versa. Code tells you *that* something writes to a table; it doesn't tell you whether that's supposed to be the only writer. Surface this as a structured question per table, e.g.: *"Table `billing_invoice` is written by `InvoiceService.markPaid` in this repo. Is this the only writer, or do other services also write to it?"*

## 6. operations.md
**Purpose**: how this service is deployed, scaled, and kept healthy.
**Evidence**: signals.deployment (Dockerfile, compose, k8s/helm manifests, CI workflow files).
**Interview-worthy**: anything about the deployment environment that lives outside the repo — actual replica counts, autoscaling policy if it's set via a platform UI rather than checked-in config, on-call rotation/paging setup. Don't guess at production topology from a Dockerfile alone.

## 7. observability.md
**Purpose**: what's actually instrumented — logging, metrics, tracing — versus what's silent.
**Evidence**: signals.observability (Micrometer/OpenTelemetry imports, `@Timed`, logging config files).
**Note**: this is the one category where you should be *actively skeptical* of apparent coverage. The presence of a logging framework or Micrometer dependency doesn't mean failures are actually surfaced with useful diagnostic content — that gap (logs exist but don't carry fault-specific semantics) is a well-documented failure mode in agent-generated and human-written code alike. Report what's instrumented *and* flag any exception-handling code (from `error_handling` evidence) that has no corresponding log statement nearby, rather than assuming instrumentation is adequate just because it exists.
**Interview-worthy**: whether there's a dashboard/alerting setup that lives outside this repo (Datadog, Grafana, etc.) worth linking to — code can't tell you that.

## 8. troubleshooting.md
**Purpose**: known error conditions and how to diagnose them.
**Evidence**: signals.error_handling (`@ControllerAdvice`/`@ExceptionHandler`), cross-referenced with observability evidence for what actually gets logged when each handler fires.
**Interview-worthy**: real incident history ("this table lock has bitten us twice") that wouldn't show up in code at all. Ask if there's a runbook, incident channel, or postmortem doc to link rather than duplicate.

## 9. configuration.md
**Purpose**: what's configurable, where, and what the defaults mean.
**Evidence**: signals.configuration (`@ConfigurationProperties`, `@Value`, `application*.yml/properties` files).
**Interview-worthy**: which config values differ by environment in ways not visible in the repo (e.g. secrets injected at deploy time, values set only in a platform's config UI). Don't fabricate example values for secrets — say "value supplied at deploy time, not in repo" instead.

## 10. change_impact.md
**Purpose**: "if you touch X, check Y" — a map from internal modules/tables/endpoints to what depends on them.
**Evidence**: arch (module dependency edges), database.md's table ownership data, integrations.md's "who calls us" answers.
**Interview-worthy**: this file is the most interview-dependent of the fourteen — it's fundamentally about *external* dependents (other teams' services, downstream consumers, batch jobs) that this repo's code cannot see. Build the *internal* half (which modules in this repo depend on which other modules — that's just the architecture graph) from code, then explicitly ask: "Beyond the consumers already named in integrations.md, is there anything else — a batch job, a report, a downstream team — that would break if `<specific module/table/endpoint>` changed shape?"

## 11. glossary.md
**Purpose**: domain vocabulary — what the business terms in the code actually mean.
**Evidence**: summaries (entity/DTO names, recurring domain nouns across `group_function` fields), signals.persistence (entity class names).
**Interview-worthy**: ambiguous or overloaded terms. If the same word means different things in different modules (a classic sign of accumulated business complexity), or if an entity name doesn't obviously map to a plain-English definition, ask rather than invent a confident-sounding definition. A glossary entry that's wrong is worse than one that's missing.

## 12. local_development.md
**Purpose**: how to get this running on a laptop.
**Evidence**: signals.deployment (docker-compose for local deps), signals.configuration (profiles like `application-local.yml`), build tool detection (`pom.xml` vs `build.gradle`/`build.gradle.kts`).
**Interview-worthy**: anything that requires access outside the repo — VPN, internal artifact repository credentials, seed data that lives in a separate system. Note these as prerequisites rather than omitting them or guessing at values.

## 13. testing.md
**Purpose**: how this repo is tested and what conventions to follow when adding tests.
**Evidence**: signals.testing (`@SpringBootTest`, Testcontainers usage), summaries of files under a test source root.
**Interview-worthy**: coverage targets or testing policy that's a team norm rather than something enforced in code (e.g. "we require integration tests for anything touching billing_invoice" isn't visible in a coverage report).

## 14. known_limitations.md
**Purpose**: known gaps, deliberate shortcuts, and things that are technically debt rather than design.
**Evidence**: TODO/FIXME comments (worth a dedicated grep pass if not already surfaced by file-summarizer), deprecated-annotation usage.
**Interview-worthy**: this is almost entirely an interview file. Code can surface *candidates* (TODO comments, deprecated APIs still in use) but "known limitation" is inherently a claim about intent and awareness that only a person can confirm. Present the code-derived candidates as a checklist ("here's what looks like a shortcut — confirm or correct each") rather than asserting them as established fact.

---

## General rule across all fourteen

This is the same rule as `doc-writer.md`'s Rule 1, stated here for reference — the two must stay in sync; if you edit one, edit the other. Every substantive claim in every generated file ends with a bracketed tag, in exactly one of these forms (a required format, not a category to paraphrase):

1. `[Evidenced — path/File.java:42]` — the specific file (and line, for a claim about one spot in it) the claim comes from. A whole-file claim just cites the file: `[Evidenced — build.gradle]`.
2. `[Confirmed — interview, <date>]` — so staleness is visible later.
3. `[Unknown — not evidenced in code, not covered in interview]`. Do not fill this category with a guess dressed up as either of the other tags.
4. `[Evidenced — path/File.java:42; inference avoided beyond this]` — optional. Signals real code evidence exists but the writer deliberately didn't stretch it into a claim the evidence doesn't actually support, so a reader can tell "nothing here" apart from "something here, deliberately not extrapolated."
5. `[Per existing docs — path, unverified against code]` — for claims sourced from documentation that predates this pipeline (an existing README, a pre-existing `docs/` folder, an old wiki page) rather than from the code or the interview. See "What counts as code evidence" above — prior documentation is a distinct, lower-trust provenance from either code or a live interview answer, since it can simply be wrong or stale.
