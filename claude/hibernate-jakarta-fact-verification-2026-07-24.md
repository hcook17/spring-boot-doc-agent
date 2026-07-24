# Fact-Verification: Hibernate ORM & Jakarta Persistence Technical Claims (as of July 24, 2026)

## TL;DR
- Of the eight claim groups, seven are **CONFIRMED** against primary sources; the one substantive correction is Claim 6: Hibernate's `@View` annotation was introduced in **6.3** (not 6.4), per every version's Javadoc "Since: 6.3" field.
- The version-pinned specifics all hold: current stable line is **7.4** with **7.4.6.Final** ("Version 7.4.6.Final Last updated 2026-07-19" per the 7.4 Migration Guide); **7.0.0.Final released 2025-05-19** and migrated to Jakarta Persistence 3.2; `@Where`/`@WhereJoinTable` were deprecated since 6.3 and removed in 7.0; `@SoftDelete` and `@View` are still `@Incubating` in 7.4.
- One nuance on Claim 2 (the javax→jakarta package move happened in **6.0**, not 7.0) and one on Claim 3 (JPA 3.2's spec document is dated April 10, 2024, but Eclipse/GitHub records give later dates).

## Key Findings

**Claim 1 — Current stable line / 7.4.6.Final / support statuses / 8.0 — CONFIRMED.** The Hibernate ORM releases page lists: "8.0 development | 7.4 latest stable | 7.3 limited-support | 6.6 limited-support." The 7.4 Migration Guide and What's New guide both show "Version 7.4.6.Final Last updated 2026-07-19." Hibernate 8.0 is in active development (8.0.0.Alpha1 dated February 02, 2026; 8.0.0.Beta1 dated 2026-06-16), targeting Jakarta Persistence 4.0.

**Claim 2 — 7.0.0.Final on 2025-05-19 / Jakarta Persistence 3.2 — CONFIRMED (with nuance).** 7.0.0.Final released May 19, 2025. The 7.0 Migration Guide states "7.0 migrates to Jakarta Persistence 3.2." However, the javax→jakarta package move happened earlier, in Hibernate **6.0** — not in 7.0.

**Claim 3 — Jakarta Persistence 3.2 finalized April 10, 2024 — PARTIALLY CONFIRMED.** The spec document itself is dated April 10, 2024, but other official records give later dates.

**Claim 4 — `@Where`/`@WhereJoinTable` deprecated since 6.3, removed in 7.0 — CONFIRMED.** The 6.6 Javadoc shows `@Deprecated(since="6.3")` on `@Where`. The 7.0 Migration Guide lists "Removed @Where and @WhereJoinTable → use @SQLRestriction or @SQLJoinTableRestriction."

**Claim 5 — `@SoftDelete` introduced 6.4, still `@Incubating` in 7.x — CONFIRMED.** Javadoc header: `@Incubating public @interface SoftDelete`, "Since: 6.4." Still `@Incubating` in the 7.0, 7.2, and 7.4 Javadocs.

**Claim 6 — `@View` annotation — CONFIRMED with correction.** `@View` exists in `org.hibernate.annotations`, distinct from `@Subselect`, DDL-exportable. It was introduced in **6.3** (not 6.4 — the document's flagged uncertainty resolves to 6.3). Still `@Incubating` in 7.4.

**Claim 7 — `org.hibernate.mapping` package — CONFIRMED.** The 7.0 Javadoc package summary lists the named classes and describes them as the mapping model.

**Claim 8 — jqa-jpa2-plugin archived — CONFIRMED.** Archived by owner on Apr 21, 2023; superseded by jqassistant-jee-plugin; **0 stars, 1 fork, 1 watching**.

## Details

### Claim 1: Current stable release line
The official Hibernate ORM releases page (hibernate.org/orm/releases/) consistently shows the navigation: **8.0 development, 7.4 latest stable, 7.3 limited-support, 6.6 limited-support**. So:
- **Current stable line: 7.4.** CONFIRMED.
- **7.4.6.Final as latest patch (dated 2026-07-19):** CONFIRMED. The 7.4 Migration Guide states verbatim "Version 7.4.6.Final Last updated 2026-07-19 00:19:12 UTC" and the What's New in 7.4 guide gives "Last updated 2026-07-19 00:21:10 UTC." The documentation index lists 7.4.5.Final dated 2026-07-12 as the immediately prior patch, consistent with 7.4.6 being newer.
- **6.6 and 7.3 support status:** Both are "limited-support." CONFIRMED. Note the labels shifted over time — earlier snapshots (when 7.3 was newest) showed 7.3 as "latest stable" and 7.2/7.1 as limited-support; the current state has 7.4 stable, 7.3 and 6.6 limited-support.
- **Hibernate 8.0 in active development:** CONFIRMED. 8.0 is labeled "development." The Hibernate ORM 8.0 releases page lists "8.0.0.Beta1 · 2026-06-16 · ASL v2 · Jakarta Persistence 4.0," and Steve Ebersole's In Relation To announcement (June 16, 2026) states 8.0.0.Beta1 "Implements support for Jakarta Persistence 4.0 - all features defined through the M5 release are supported and both the Jakarta Persistence and Jakarta Data TCKs are passing." The Hibernate changelog records "Changes in 8.0.0.Alpha1 (February 02, 2026)" including "HHH-20028 Update to Jakarta Persistence 4.0."

### Claim 2: 7.0.0.Final release and Jakarta Persistence 3.2
- **7.0.0.Final on May 19, 2025:** CONFIRMED (the Hibernate release record; Wikipedia's infobox lists "Stable release: 7.0.0.Final / May 19, 2025"). The release announcement is published at in.relation.to/2025/05/19/orm-70/.
- **7.0 migrates to Jakarta Persistence 3.2:** CONFIRMED. The 7.0 Migration Guide states "Hibernate now baselines on Java 17… 7.0 migrates to Jakarta Persistence 3.2 which is fairly disruptive, mainly around" the Entity Graph API and related changes. This was the plan of record: Gavin King's In Relation To post "A summary of Jakarta Persistence 3.2" (April 1, 2024) states "our implementation of JPA 3.2 is very well advanced, and will be delivered later this year as Hibernate 7.0."
- **javax→jakarta package move:** This was NOT done in 7.0. The 6.0 Migration Guide states "6.0 moves from Java Persistence… to Jakarta Persistence… applications would need to be updated to use the Jakarta Persistence classes (jakarta.persistence.*) instead of the Java Persistence ones (javax.persistence.*)." So the annotation package move (javax.persistence.* → jakarta.persistence.*) happened in **Hibernate 6.0** (JPA 3.0), while 7.0's Jakarta Persistence step was the 3.1→3.2 upgrade. The document's framing ("or was that already done in an earlier line") resolves to: yes, done earlier, in 6.0.

### Claim 3: Jakarta Persistence 3.2 finalization date
There is a genuine date discrepancy across official sources:
- The **spec document** (jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html) header reads: "Specification: Jakarta Persistence Version: 3.2 Status: Final Release **Release: April 10, 2024**."
- The **Eclipse project release page** (projects.eclipse.org/projects/ee4j.jpa/releases/3.2) lists "Release Date: Tuesday, April 30, 2024."
- The **Specification Committee Ballot** concluded successfully on 2024-05-20.
- **API artifact dates diverge**: Wikidata records the GitHub tag `3.2-3.2.0-RELEASE` publication date as September 20, 2024, whereas the tagged `jakarta.persistence-api` 3.2.0 Maven artifact is dated April 24, 2024 per MvnRepository.

So the claim "finalized/released April 10, 2024" is CONFIRMED as printed on the spec document itself, but readers should note the surrounding process/artifact dates differ. If a single canonical figure is needed, **"April 2024"** is safest.

### Claim 4: @Where / @WhereJoinTable removal
- **`@Where` deprecated since 6.3:** CONFIRMED verbatim. The 6.6 Javadoc for `org.hibernate.annotations.Where` shows the declaration `@Target(...) @Retention(RUNTIME) @Deprecated(since="6.3") public @interface Where` with "Deprecated. Use SQLRestriction."
- **Removed in 7.0, replaced by `@SQLRestriction`:** CONFIRMED. The 7.0 Migration Guide's removed-annotations list: "Removed @Where and @WhereJoinTable → use @SQLRestriction or @SQLJoinTableRestriction."
- **`@WhereJoinTable` removed in 7.0, replaced by `@SQLJoinTableRestriction`:** CONFIRMED, same migration-guide line.

**Why this matters beyond completeness:** a repo on Hibernate 6.x may legitimately use `@Where`; the same source will not compile on 7.x. Version is therefore a correctness input to any static scan, not metadata — the assumed baseline must be recorded per scan.

### Claim 5: @SoftDelete
- **Introduced in 6.4:** CONFIRMED. The Javadoc shows "Since: 6.4," and the Hibernate 6.4.0.CR1 release blog (Steve Ebersole, Oct 26, 2023) announces "6.4 adds support for soft deletes using the new @SoftDelete annotation."
- **Still `@Incubating` in 7.1 and in the current 7.4 line:** CONFIRMED. The declaration is `@Target({PACKAGE,TYPE,FIELD,METHOD,ANNOTATION_TYPE}) @Retention(RUNTIME) @Documented @Incubating public @interface SoftDelete` across the 6.6, 7.0, 7.2 and 7.4/stable Javadocs. (Individual optional elements `options` and `comment` carry their own "Since: 7.0" markers, but the annotation type itself remains "Since: 6.4" and `@Incubating`.)

### Claim 6: @View annotation
- **Exists in `org.hibernate.annotations`, distinct from `@Subselect`:** CONFIRMED. The Javadoc: "Maps an entity to a database view… This annotation specifies the query which defines the view, allowing the view to be exported by the schema management tooling," with the worked `@View(query="select …")` → `create view summary as …` DDL example. It is a separate annotation from `@Subselect`.
- **DDL-exportable via schema management tooling:** CONFIRMED (explicit in the Javadoc, as above).
- **Introduced in 6.3 or 6.4?** The document flagged this as uncertain. **It is 6.3.** Every version's Javadoc "Since:" field (6.4, 6.6, and 7.4/stable) reads "Since: 6.3," and the `@View` page already exists in the 6.3 Javadocs (confirmed via the 6.3 package-summary index, which lists View with a live link). The document's alternative guess of 6.4 is INCORRECT.
- **Currently `@Incubating`:** CONFIRMED. Declaration in 7.4/stable: `@Incubating @Target(TYPE) @Retention(RUNTIME) public @interface View`.

### Claim 7: org.hibernate.mapping package sanity check
CONFIRMED. The 7.0 Javadoc package summary for `org.hibernate.mapping` lists the mapping model objects and describes them as: "The mapping model objects represent: Java elements with a persistent representation, for example, a PersistentClass, Collection, or Property, and objects in a relational database, for example, a Table, Column, or ForeignKey." It further explains "It is the responsibility of the metadata binders… to process a set of annotated classes and produce fully-initialized mapping model objects," which "are then passed to the constructor of SessionFactoryImpl." Individual classes confirmed present in the 7.0 Javadoc: PersistentClass, RootClass, Subclass (with direct subclasses JoinedSubclass, SingleTableSubclass, UnionSubclass — the latter "a mapping model object that represents a subclass in a 'union' or 'table per concrete class' inheritance hierarchy"), Table, Column, Formula, ForeignKey, UniqueKey, Index, PrimaryKey, Join, Collection, Property, Component, Any, Value, DependantValue, CheckConstraint ("Represents a table or column level check constraint"), and Backref. This is Hibernate's own boot-time mapping model consumed by schema-export/DDL tooling.

### Claim 8: jQAssistant JPA plugin
CONFIRMED. The GitHub repo jqassistant-archive/jqa-jpa2-plugin ("jQAssistant JPA 2 Plugin") states in its README: "This project has been archived and is no longer actively developed. It has been superseded by the jqassistant-jee-plugin." The repository banner reads "This repository was archived by the owner on **Apr 21, 2023**. It is now read-only." Its metrics are **0 stars, 1 fork, 1 watching**. It is distinct from the newer jqassistant-jee-plugin under the jqassistant-plugin org.

## Recommendations
- **Treat Claims 1, 2, 4, 5, 7, 8 as verified** and safe to cite directly against the primary sources noted (Hibernate release/migration pages, Javadocs, GitHub).
- **Correct Claim 6 in the source document**: change "@View introduced in 6.3 or 6.4 (uncertain)" to "introduced in 6.3 (confirmed via Javadoc 'Since' field and the 6.3 package-summary index)." *(Applied in the survey's 2026-07-24 review-pass-2 revision.)*
- **Clarify Claim 2's phrasing**: the javax→jakarta annotation package migration is a Hibernate 6.0 (JPA 3.0) change; Hibernate 7.0's Jakarta step is the move to JPA 3.2. Do not attribute the javax→jakarta move to 7.0. *(Applied.)*
- **Add a footnote to Claim 3**: cite "April 10, 2024" as the date printed on the spec document, while noting the Eclipse release record (April 30, 2024), the Specification Committee Ballot (May 20, 2024), and divergent API-artifact dates. If a single canonical date is needed, "April 2024" is safest. *(Applied.)*
- **Prefer Hibernate's own 7.0 Migration Guide over the Quarkus 3.24 migration guide** when citing the `@Where` removal — the Quarkus guide restates it accurately but is downstream. *(Applied.)*
- **Benchmarks that would change these conclusions**: a new 7.4.x patch (7.4.7+) or promotion of 7.4 out of "latest stable" (e.g. 8.0.0.Final shipping) would supersede Claim 1; graduation of `@SoftDelete`/`@View` out of `@Incubating` in a future release would change Claims 5/6.

## Caveats
- The subagent could not fetch the literal `/orm/7.4/javadocs/...` URL path for `@View`/`@SoftDelete`; it verified the same content via the `docs.hibernate.org/stable/core/javadocs/...` alias (which the site currently serves as 7.4 latest stable, Copyright 2001-2026, Java 17/Jakarta 11) and the identical docs.jboss.org mirror. The 7.4-line `@Incubating`/`Since` values are corroborated across the 6.4, 6.6, 7.0, and 7.2 Javadocs, which all agree.
- The 6.3 `@View` page body could not be fetched directly (tool permission), but its existence and "Since: 6.3" are confirmed via the 6.3 package-summary index plus the identical "Since" field on all later pages.
- Jakarta Persistence 3.2 release dating is genuinely inconsistent across official Eclipse/Jakarta sources (see Claim 3); this is flagged rather than resolved to a single number.
- Some secondary corroboration (Wikipedia infobox for the 2025-05-19 date; Medium/blog posts for deprecation narratives) was used only to cross-check primary sources, not as the primary citation. All annotation `@Deprecated`/`@Incubating`/`Since` facts and the migration-guide removals rest on the official Hibernate Javadocs and migration guides.

## Consumers of this document
- `claude/10-architecture-maturation-plan.md` — 1.1.3 (predicate vocabulary version pin), 1.3.4 (per-scan Hibernate baseline).
- `claude/jpa-hibernate-predicate-vocabulary-survey.md` — every version-sensitive claim in its Category tables and Caveats section.
