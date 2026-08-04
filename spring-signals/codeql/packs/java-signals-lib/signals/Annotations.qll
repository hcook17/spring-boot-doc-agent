/**
 * Annotation resolution that matches how frameworks actually resolve
 * annotations, rather than how they are spelled.
 *
 * Two mechanisms are modelled:
 *
 *  1. META-ANNOTATION TRANSITIVITY. Spring resolves via
 *     `AnnotatedElementUtils.findMergedAnnotation`, walking meta-annotations
 *     transitively. `@RestController` IS-A `@Controller` IS-A `@Component`;
 *     `@SpringBootApplication` IS-A `@Configuration`. Direct FQN equality
 *     misses all of it. In ocs-api-service that is 48 controllers plus the
 *     Application class that a direct-match stereotype rule scores as zero.
 *
 *  2. REPEATABLE CONTAINERS (Java 8+). `getAnAnnotation()` on a repeated
 *     annotation returns the *container*, not the members. ocs-api-service has
 *     `@NamedNativeQuery` repeated on entity classes, i.e. 9 declarations that
 *     a naive rule reads as some smaller number of `@NamedNativeQueries`.
 */

import java
private import codeql.util.Unit

/**
 * Holds if `t` is, or is transitively meta-annotated with, the annotation type
 * `pkg.name`.
 *
 * `java.lang.annotation` is excluded from the walk: every annotation type
 * carries `@Retention`/`@Target`/`@Documented`, and `@Documented` is annotated
 * with itself. CodeQL's fixpoint terminates on the cycle regardless, but the
 * exclusion keeps the relation small.
 *
 * CAVEAT -- UNVERIFIED AGAINST A BUILT DATABASE. This depends on CodeQL
 * extracting annotations that sit on library annotation types (e.g. the
 * `@Component` on the jar-resident `RestController`). Spring's annotations are
 * RUNTIME-retained so they are present in the class files, but extractor
 * behaviour for library metadata should be confirmed before the meta-annotation
 * counts are trusted. See codeql/packs/spring-signals/Probe.ql for the probe.
 */
predicate metaAnnotatedWith(RefType t, string pkg, string name) {
  t.getSourceDeclaration().hasQualifiedName(pkg, name)
  or
  exists(Annotation meta |
    meta = t.getSourceDeclaration().getAnAnnotation() and
    not meta.getType().getPackage().hasName("java.lang.annotation") and
    metaAnnotatedWith(meta.getType(), pkg, name)
  )
}

/**
 * EXTENSION POINT: a framework's documented meta-annotation graph.
 *
 * This library pack is language-scoped and framework-agnostic. It must not know
 * that Spring exists. An earlier version imported `signals.Catalog` to reach
 * Spring's `metaEdge` table, which made the "framework-agnostic library" claim
 * false and would have dragged Spring facts into any Micronaut or Quarkus pack
 * that depended on this one.
 *
 * The dependency is now inverted. The library declares the shape of the graph;
 * each framework query pack contributes its own edges by extending this class.
 * See spring-signals/SpringMetaEdges.qll.
 *
 * A contributed edge must be verifiable from the framework's own source. It is a
 * published API contract, which is why edges here are trusted without a probe --
 * unlike `metaAnnotatedWith`, which infers edges from extracted metadata.
 */
abstract class MetaAnnotationEdges extends Unit {
  /** Holds if `pkg`.`name` is meta-annotated with `superPkg`.`superName`. */
  abstract predicate edge(string pkg, string name, string superPkg, string superName);
}

/** Holds if any contributed source declares this edge. */
predicate declaredMetaEdge(string pkg, string name, string superPkg, string superName) {
  any(MetaAnnotationEdges src).edge(pkg, name, superPkg, superName)
}

/**
 * Transitive closure of the contributed edges.
 *
 * Not reflexive: `isOrMeta` already has `isExactly` as its first disjunct, so a
 * reflexive case here would be dead weight and would need an endpoint predicate
 * to stay finite.
 */
predicate declaredMetaReaches(string pkg, string name, string superPkg, string superName) {
  declaredMetaEdge(pkg, name, superPkg, superName)
  or
  exists(string mp, string mn |
    declaredMetaEdge(pkg, name, mp, mn) and
    declaredMetaReaches(mp, mn, superPkg, superName)
  )
}

/**
 * FAIL-CLOSED SWITCH for meta-annotation resolution.
 *
 * Defined as `none()`, which disables ONLY the DISCOVERED half of meta
 * resolution -- the transitive walk over extracted annotation metadata.
 * A framework's documented meta-annotation graph, contributed via
 * `MetaAnnotationEdges`, is always available, so the closed state is NOT "exact match".
 *
 * The distinction matters in both directions. Shipping the discovered half
 * enabled-by-default would let counts derived from an unverified extractor
 * assumption flow into exit criteria as product truth. But describing the
 * closed state as exact-only understates it, which is its own failure: it
 * teaches a reader to distrust numbers that are in fact contract-backed.
 *
 * TO ENABLE: run `codeql/packs/spring-signals/Probe.ql` against a real database.
 * If it reports a non-zero count for the library-annotation control case,
 * replace the body with `any()` in the same PR that records the probe output.
 * Do not enable it speculatively; a wrong meta count is worse than no meta
 * count, because it looks like a recall improvement.
 */
predicate metaResolutionEnabled() { none() }

/**
 * Holds if `a` is `pkg.name`, or -- once `metaResolutionEnabled()` holds --
 * is transitively meta-annotated with it.
 *
 * WHAT THE CLOSED STATE COVERS
 *   exact match, PLUS every edge in Spring's documented meta-annotation graph.
 *   So the 48 `@RestController` classes in ocs-api-service ARE recovered with
 *   the switch closed -- the contributed graph carries `RestController -> Controller`, and
 *   that is a published Spring API contract readable from Spring source, not an
 *   extractor inference. It needs no probe and may be claimed in wave 1.
 *
 * WHAT THE CLOSED STATE DOES NOT COVER
 *   any meta edge NOT in the table: project-local composed stereotypes, and
 *   third-party framework annotations nobody has catalogued. Recall over that
 *   set is what the probe gates, and it is what must not be claimed until the
 *   probe passes.
 *
 *   On ocs-api-service that set is empty -- the repo declares zero `@interface`
 *   types -- so closed-state recall equals open-state recall there. That is a
 *   property of this repo, not of the pack; it does not transfer to a sibling
 *   service without re-checking `first_party_annotation_types`.
 */
predicate isOrMeta(Annotation a, string pkg, string name) {
  isExactly(a, pkg, name)
  or
  // Contributed framework edges, available regardless of the switch. Without
  // these the closed state is a RECALL REGRESSION against the pack this
  // replaces: `isOrMeta(a, "...stereotype", "Controller")` would match only
  // literal `@Controller` and drop all 48 `@RestController` classes in
  // ocs-api-service. See spring-signals/SpringMetaEdges.qll.
  exists(string p, string n | isExactly(a, p, n) and declaredMetaReaches(p, n, pkg, name))
  or
  // Discovered chains -- project-local composed annotations, and any framework
  // edge not in the table. Gated on the probe.
  metaResolutionEnabled() and metaAnnotatedWith(a.getType(), pkg, name)
}

/** Holds if `a` is exactly `pkg.name`, ignoring meta-annotations. */
predicate isExactly(Annotation a, string pkg, string name) {
  a.getType().getSourceDeclaration().hasQualifiedName(pkg, name)
}

/**
 * Gets an annotation on `a`, expanding repeatable containers one level.
 *
 * Over-approximation: this also yields annotations nested inside a non-container
 * array attribute named `value`. Under-approximation: containers whose array
 * attribute is not named `value` are not expanded (the JLS convention is
 * `value()`, so this is rare). Both are acceptable for inventory counting;
 * neither is acceptable for a rule that asserts uniqueness.
 */
Annotation getAnEffectiveAnnotation(Annotatable a) {
  result = a.getAnAnnotation()
  or
  exists(Annotation container |
    container = a.getAnAnnotation() and
    result = container.getValue("value").(ArrayInit).getAnInit()
  )
}

/** Gets the fully-qualified name of an annotation type, for the `detail` column. */
string annotationFqn(Annotation a) {
  result = a.getType().getSourceDeclaration().getPackage().getName() + "." +
      a.getType().getSourceDeclaration().getNestedName()
}

/**
 * Holds if `a` is an annotation whose *package* matches `pattern`.
 *
 * Package-level matching is deliberately available alongside FQN matching.
 * ocs-api-service writes 540 occurrences of
 * `@io.swagger.v3.oas.annotations.media.Content` fully qualified inline, which
 * leaves no `Import` node at all -- so any import-based rule for that namespace
 * undercounts badly while an annotation-type rule does not.
 */
bindingset[pattern]
predicate annotationPackageMatches(Annotation a, string pattern) {
  a.getType().getSourceDeclaration().getPackage().getName().regexpMatch(pattern)
}
