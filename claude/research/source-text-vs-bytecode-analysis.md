# Source-text (ast-grep/tree-sitter) vs. compiled-bytecode/ArchUnit analysis

Research note backing the upgrade-path sentence in `README.md`'s "On the deterministic scan" section. Not a steering prompt, not wired into any pipeline stage — a decision doc, kept in-repo for now.

## 1. This project's current approach

`scripts/spring_signal_scan.py` runs all Java structural detection through [ast-grep](https://ast-grep.github.io/) (tree-sitter-based AST matching over raw source text — see `scripts/spring_ast_grep_rules.yml`), not regex and not bytecode. README.md states the tradeoff directly:

> It's still source-text analysis, not bytecode — no build step or classpath required, at some cost in precision (it won't resolve inherited annotations or interfaces implemented indirectly).

And on the upgrade path:

> If you want still higher fidelity later (resolved inheritance, annotations picked up via meta-annotations), swapping in an ArchUnit-based scanner (which analyzes compiled bytecode) is a reasonable next upgrade path; the JSON output shape is deliberately simple so that swap wouldn't require touching the rest of the pipeline.

The rule file itself (`spring_ast_grep_rules.yml`) shows the current ceiling concretely: `persistence__entity` and `persistence__repository` are already `kind`+`has` relational rules (not literal patterns) specifically so *order and adjacency* of annotations on a single declaration don't matter — but they still only see what's written in that one file's syntax tree. They cannot follow `extends` up a class hierarchy, cannot resolve an annotation attached only via a custom meta-annotation (e.g. a project-defined `@MyRestController` that itself carries `@RestController`), and cannot see an interface implemented through a chain of abstract classes.

## 2. What bytecode/ArchUnit-style analysis buys and costs

**Buys:**
- **Resolved inheritance.** Bytecode carries the fully-linked class hierarchy; a scanner can walk up through superclasses/superinterfaces to find an annotation or capability the source file itself never mentions.
- **Meta-annotation resolution.** The JVM (and libraries built on top of bytecode, like Spring's own `AnnotatedElementUtils`) can walk annotations-on-annotations to discover, e.g., that a custom `@ServiceEndpoint` meta-annotation is itself meta-annotated with `@RestController`. Source-text matching only sees the literal annotation token used at the call site.
- **Indirect interface implementation.** Because bytecode resolves the full type graph, "does this class implement `Repository`" can be answered even when the `implements`/`extends` clause is several hops away.
- ArchUnit specifically (confirmed via its own docs, see Sources) analyzes compiled `.class` files through a `ClassFileImporter`, building a full `JavaClass`/`JavaPackage` object model; its rule DSL runs against that resolved model, not source text.

**Costs:**
- **Requires a build.** ArchUnit fundamentally needs compiled bytecode — "compilation is prerequisite," per its own user guide. That breaks this project's core design goal: point `document-spring-repo` at *any* Spring Boot repo and get output with no build step, no classpath assembly, no dependency resolution.
- **Classpath assembly is nontrivial and partially unsolved even by ArchUnit itself.** Its docs note that without classpath access, annotation attributes are only reachable through an untyped `JavaAnnotation<?>` API (no type safety); with classpath access, ArchUnit will "search within the classpath for missing classes and import them," which is both a setup burden (someone has to supply a working classpath for an arbitrary target repo) and a performance cost. For a docs-generation pipeline meant to run against unfamiliar third-party repos sight-unseen, assembling a correct classpath per target is a real, recurring integration problem — not a one-time cost.
- **Annotations aren't free of ambiguity in bytecode either.** The ACM paper "Understanding and Detecting Annotation-Induced Faults of Static Analyzers" (Zhang, Pei, Liang, Tan — FSE 2024) found that annotations "can change program structures and convey semantics information without awareness of static analyzers," causing real, catalogued faults across PMD, SpotBugs, Infer, SonarQube, and Soot — some of which do operate on bytecode/IR. Moving to bytecode raises the analysis ceiling but does not eliminate annotation-handling bugs as a class.
- Java retention policy matters here too: `@Retention(RetentionPolicy.SOURCE)` annotations vanish entirely at compile time and are invisible to *any* bytecode-based tool — a possible edge case worth flagging if a hybrid is ever built, though none of Spring's own framework annotations (`@RestController`, `@Entity`, etc.) use `SOURCE` retention, so it's not a concern for the current rule set.

## 3. Survey

### GitHub repos (via `gh search repos`, sorted by stars; all checked for a push within the last ~12 months)

| Repo | Stars | Last push | Relevance |
|---|---|---|---|
| [ast-grep/ast-grep](https://github.com/ast-grep/ast-grep) | 15,172 | 2026-07-23 | The tool this project already depends on; tree-sitter-based structural search, source-text only, no build step — confirms the "what it can't resolve" side of the tradeoff. |
| [TNG/ArchUnit](https://github.com/TNG/ArchUnit) | 3,782 | 2026-07-23 | The named upgrade path in README.md; bytecode importer (`ClassFileImporter`), resolves inheritance and (with classpath) type-safe annotation access. |
| [TNG/ArchUnitNET](https://github.com/TNG/ArchUnitNET) | 1,330 | 2026-07-23 | Same design family, .NET/IL bytecode instead of JVM — corroborates that the bytecode-analysis pattern generalizes across compiled-CLR/JVM ecosystems, not JVM-specific. |
| [jQAssistant/jqassistant](https://github.com/jQAssistant/jqassistant) | 283 | 2026-07-16 | Hybrid: uses ASM to read both source and bytecode into a Neo4j graph; shows a middle path between pure source-text and pure bytecode, at the cost of a Maven build + graph DB dependency. |
| [tree-sitter/tree-sitter-java](https://github.com/tree-sitter/tree-sitter-java) | 271 | 2025-12-15 | The grammar underlying ast-grep's Java support; confirms tree-sitter parses full-fidelity concrete syntax trees from source text alone, no semantic/type resolution layer. |

### Deepwiki architecture summaries consulted (DFS on ArchUnit, then BFS across ast-grep and jQAssistant)

- `deepwiki.com/TNG/ArchUnit` — confirmed `ClassFileImporter` → `JavaClass`/`JavaPackage` object model built from bytecode; page didn't itself detail meta-annotation resolution, so followed up directly against `archunit.org`'s user guide (below).
- `deepwiki.com/ast-grep/ast-grep` — confirmed layered architecture over tree-sitter via the `ast-grep-language` crate, operating purely at the syntactic level with no type/annotation-inheritance resolution — matches this project's own documented limitation.
- `deepwiki.com/jQAssistant/jqassistant` — confirmed hybrid source+bytecode scanning via ASM into Neo4j, with a Maven-lifecycle build requirement.

### Papers

- Huaien Zhang, Yu Pei, Shuyun Liang, Shin Hwei Tan, ["Understanding and Detecting Annotation-Induced Faults of Static Analyzers"](https://arxiv.org/abs/2402.14366), FSE/ACM PACMSE 2024 — catalogues real annotation-handling faults across six widely-used static analyzers (including bytecode/IR-based ones), evidence that bytecode resolution raises but doesn't remove annotation-precision risk.
- ["Comparison of Static Analysis Architecture Recovery Tools for Microservice Applications"](https://arxiv.org/html/2412.08352v1) — empirically compares source-level and bytecode-based (MicroGraal, on GraalVM native-image bytecode) architecture-recovery tools; MicroGraal had *recall of 0* on connections and endpoints ("the tool produced empty results for all applications in the dataset we used"), and was the slowest tool in the study (~60s/app avg vs. ~0.03-0.04s for the others) — not just "no advantage" but the worst performer on both axes. Caveat: this reads as much like a GraalVM-native-image-compatibility failure for that specific tool as a general property of bytecode analysis — the paper's own conclusion that "achieving a high recall requires a deeper analysis of the source code beyond deployment files" suggests depth of analysis logic mattered more than source-vs-bytecode as the input format.

## 4. Recommendation for this project

**Stay source-text-only for now; don't build a bytecode/ArchUnit stage.** Three reasons, in order of weight:

1. **The core design goal is incompatible with a build requirement.** This pipeline's whole pitch is "point it at a repo, no build step, no classpath." ArchUnit's own docs confirm bytecode import is a hard prerequisite, and that even it falls back to a degraded, untyped API when a full classpath isn't supplied. Assembling a working classpath for an arbitrary, unfamiliar target repo (the exact scenario `document-spring-repo` is built for) is a real per-target integration burden, not a one-time setup cost — it would need to run in a live user session, against an unknown build tool/dependency set/Java version, every time.
2. **The empirical evidence doesn't clearly favor bytecode.** The architecture-recovery survey's bytecode-based tool (MicroGraal) had recall of 0 on two of three characteristics and was the slowest tool in the study — though that specific result looks at least partly like a tool/environment compatibility failure rather than a provable general property of bytecode analysis. Either way, it's not evidence that bytecode is a strictly-dominant approach, and the annotation-fault paper shows bytecode analysis has its own precision failure modes — just a different tradeoff point, not a clearly better one.
3. **The gap is already contained and small.** `spring_ast_grep_rules.yml`'s relational (`kind`+`has`) rules already close the *adjacency/ordering* precision gap that mattered most in practice (per the file's own comments, confirmed against a real production codebase). What's left — meta-annotations, cross-class inheritance, indirect interface implementation — is a narrower miss than the original regex-to-ast-grep rewrite fixed, and each miss degrades gracefully: a missed entity/controller/repository shows up as an `Unknown`-tagged gap for the interview stage to ask about, rather than a silent wrong answer.

**If this ever needs revisiting**, the trigger condition should be evidence-based, not speculative: a real production Spring Boot repo where the current rules produce a *silently wrong* result specifically due to meta-annotations or inherited annotations (the same bar that justified the original regex→ast-grep rewrite). Until then, the JSON output shape documented in README.md already keeps this door open cheaply — no need to open it preemptively.

If a future need does clear that bar, a **hybrid, opt-in stage** (only invoked when a build/classpath is actually available, e.g. a Maven/Gradle wrapper detected in the repo) is a better shape than replacing the current scanner outright — closer to jQAssistant's hybrid model than ArchUnit's bytecode-only one, and it preserves the no-build-step path as the default for repos where a build can't be assumed.

## Sources

- README.md, "On the deterministic scan (`spring_signal_scan.py`)" section (this repo)
- `scripts/spring_ast_grep_rules.yml` (this repo)
- [ArchUnit — Unit test your Java architecture](https://www.archunit.org/)
- [ArchUnit User Guide](https://www.archunit.org/userguide/html/000_Index.html)
- [github.com/TNG/ArchUnit](https://github.com/TNG/ArchUnit)
- [github.com/TNG/ArchUnitNET](https://github.com/TNG/ArchUnitNET)
- [github.com/ast-grep/ast-grep](https://github.com/ast-grep/ast-grep)
- [github.com/jQAssistant/jqassistant](https://github.com/jQAssistant/jqassistant)
- [github.com/tree-sitter/tree-sitter-java](https://github.com/tree-sitter/tree-sitter-java)
- [deepwiki.com/TNG/ArchUnit](https://deepwiki.com/TNG/ArchUnit)
- [deepwiki.com/ast-grep/ast-grep](https://deepwiki.com/ast-grep/ast-grep)
- [deepwiki.com/jQAssistant/jqassistant](https://deepwiki.com/jQAssistant/jqassistant)
- Zhang, Pei, Liang, Tan, ["Understanding and Detecting Annotation-Induced Faults of Static Analyzers"](https://arxiv.org/abs/2402.14366), arXiv:2402.14366 (FSE/PACMSE 2024)
- ["Comparison of Static Analysis Architecture Recovery Tools for Microservice Applications"](https://arxiv.org/html/2412.08352v1), arXiv:2412.08352
