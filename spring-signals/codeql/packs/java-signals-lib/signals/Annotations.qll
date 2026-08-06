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
import signals.Catalog

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
 * counts are trusted. See harness/verify-meta-annotations.ql for the probe.
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
 * FAIL-CLOSED SWITCH for meta-annotation resolution.
 *
 * Defined as `none()` so that `isOrMeta` degrades to exact matching. Shipping
 * transitive meta-resolution enabled-by-default while simultaneously saying the
 * underlying extractor assumption is unverified would let unverified counts
 * flow into wave 1 exit criteria and dashboards as if they were product truth.
 *
 * TO ENABLE: run `harness/probe-meta-annotations.ql` against a real database.
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
 * While the switch is off this is exactly `isExactly`, so every query that uses
 * it is safe to run and its numbers are exact-match numbers. Concretely: until
 * the probe passes, do NOT claim the 48 `@RestController` recovery in
 * ocs-api-service. That claim is a wave 4 deliverable, not a wave 1 one.
 */
predicate isOrMeta(Annotation a, string pkg, string name) {
  isExactly(a, pkg, name)
  or
  // Spring's documented meta-annotation graph, available regardless of the
  // switch. Without this the closed state is a RECALL REGRESSION against the
  // pack it replaces: `isOrMeta(a, "...stereotype", "Controller")` would match
  // only literal `@Controller` and drop all 48 `@RestController` classes in
  // ocs-api-service. See Catalog.qll::metaEdge.
  exists(string p, string n | isExactly(a, p, n) and metaReaches(p, n, pkg, name))
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
      a.getType().getSourceDeclaration().getName()
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
