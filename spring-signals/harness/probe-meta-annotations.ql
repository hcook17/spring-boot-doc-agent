/**
 * @name PROBE: is library annotation metadata extracted?
 * @description Trust gate for `metaResolutionEnabled()`. Everything in
 *              Annotations.qll assumes CodeQL extracts annotations that sit on
 *              *library* annotation types -- the `@Component` on the
 *              jar-resident `RestController`. If that does not hold, transitive
 *              meta-resolution silently returns exact-match results while
 *              claiming to be more, which is worse than not having it.
 *
 *              Run this BEFORE flipping `metaResolutionEnabled()` to `any()`.
 *              Record the output in the same PR as the flip.
 *
 *              PASS: control_meta_on_library > 0 AND
 *                    restcontroller_reaches_component = 1
 *              FAIL: either is 0 -- keep the switch closed, hardcode Spring's
 *                    own chains, and reserve the transitive predicate for
 *                    first-party composed annotations only.
 * @kind table
 * @id spring-signals/probe-meta-annotations
 */

import java
import signals.Annotations

from string check, int n
where
  // Does any library-resident annotation type carry annotations at all?
  check = "control_meta_on_library" and
  n =
    count(AnnotationType at, Annotation meta |
      at.getPackage().getName().matches("org.springframework.%") and
      meta = at.getAnAnnotation() and
      not meta.getType().getPackage().hasName("java.lang.annotation")
    )
  or
  // The specific chain the pack depends on:
  // RestController -meta-> Controller -meta-> Component.
  check = "restcontroller_reaches_component" and
  n =
    count(AnnotationType at |
      at.hasQualifiedName("org.springframework.web.bind.annotation", "RestController") and
      metaAnnotatedWith(at, "org.springframework.stereotype", "Component")
    )
  or
  // Same question for the Boot entry point.
  check = "springbootapplication_reaches_configuration" and
  n =
    count(AnnotationType at |
      at.hasQualifiedName("org.springframework.boot.autoconfigure", "SpringBootApplication") and
      metaAnnotatedWith(at, "org.springframework.context.annotation", "Configuration")
    )
  or
  // First-party composed annotations exist at all? On ocs-api-service the
  // answer is 0 -- there are no `@interface` declarations in the repo -- which
  // is itself worth knowing before investing in meta-resolution here.
  check = "first_party_annotation_types" and
  n =
    count(AnnotationType at |
      at.getFile().getRelativePath().regexpMatch("^(?:.*/)?src/main/java/.*\\.java$")
    )
  or
  // REGRESSION TEST for the closed-state hole found in review. This must hold
  // with `metaResolutionEnabled()` still CLOSED -- it exercises the hardcoded
  // Catalog.qll::metaEdge table, not the gated transitive predicate. If it is
  // 0, `api_surface__controller` is silently dropping every @RestController.
  check = "closed_state_restcontroller_is_controller" and
  n =
    count(Annotation a |
      a.getType().getSourceDeclaration()
        .hasQualifiedName("org.springframework.web.bind.annotation", "RestController") and
      isOrMeta(a, "org.springframework.stereotype", "Controller")
    )
select check, n
