/**
 * Spring's documented meta-annotation graph, contributed to the language-scoped
 * library through its `MetaAnnotationEdges` extension point.
 *
 * WHY THIS FILE EXISTS -- READ BEFORE MOVING IT BACK.
 *
 * These edges were briefly defined in `java-signals-lib/signals/Catalog.qll`, and
 * `Annotations.qll` imported them directly. That made the framework-agnostic
 * library depend on Spring, which falsified the multi-framework claim the whole
 * pack layout rests on: a Micronaut or Quarkus query pack would have inherited
 * Spring's meta-graph transitively. The dependency is now inverted -- the library
 * declares the shape, each framework pack supplies its own facts.
 *
 * WHY THESE EDGES NEED NO PROBE
 *
 * Every edge is verifiable by reading Spring source: `@RestController` is
 * annotated `@Controller`, `@Controller` is annotated `@Component`, and so on.
 * That is a published API contract. `metaAnnotatedWith` by contrast INFERS edges
 * from extracted class-file metadata, which is why it sits behind
 * `metaResolutionEnabled()`.
 *
 * This distinction is what makes the closed state safe. Without these edges,
 * `isOrMeta(a, "...stereotype", "Controller")` degrades to literal `@Controller`
 * and silently drops all 48 `@RestController` classes in ocs-api-service -- a
 * recall regression against the pack this replaces, wearing a safety label.
 *
 * INVARIANT: every edge must be verifiable from Spring source. Do not add an
 * edge because a query needs it.
 */

import java
import signals.Annotations

class SpringMetaEdges extends MetaAnnotationEdges {
  SpringMetaEdges() { this = this }
  override predicate edge(string pkg, string name, string superPkg, string superName) {
    // Stereotypes. Everything composes onto @Component.
    pkg = "org.springframework.stereotype" and
    superPkg = "org.springframework.stereotype" and
    superName = "Component" and
    name in ["Service", "Repository", "Controller"]
    or
    pkg = "org.springframework.web.bind.annotation" and
    name = "RestController" and
    superPkg = "org.springframework.stereotype" and
    superName = "Controller"
    or
    pkg = "org.springframework.context.annotation" and
    name = "Configuration" and
    superPkg = "org.springframework.stereotype" and
    superName = "Component"
    or
    // Advice.
    pkg = "org.springframework.web.bind.annotation" and
    name = "ControllerAdvice" and
    superPkg = "org.springframework.stereotype" and
    superName = "Component"
    or
    pkg = "org.springframework.web.bind.annotation" and
    name = "RestControllerAdvice" and
    superPkg = "org.springframework.web.bind.annotation" and
    superName = "ControllerAdvice"
    or
    // Boot entry point and configuration variants.
    pkg = "org.springframework.boot.autoconfigure" and
    name = "SpringBootApplication" and
    superPkg = "org.springframework.context.annotation" and
    superName = "Configuration"
    or
    pkg = "org.springframework.boot.autoconfigure" and
    name = "AutoConfiguration" and
    superPkg = "org.springframework.context.annotation" and
    superName = "Configuration"
    or
    pkg = "org.springframework.boot.test.context" and
    name = "TestConfiguration" and
    superPkg = "org.springframework.context.annotation" and
    superName = "Configuration"
    or
    // HTTP method shortcuts compose onto @RequestMapping.
    pkg = "org.springframework.web.bind.annotation" and
    superPkg = "org.springframework.web.bind.annotation" and
    superName = "RequestMapping" and
    name in ["GetMapping", "PostMapping", "PutMapping", "PatchMapping", "DeleteMapping"]
    or
    // HTTP interface client shortcuts compose onto @HttpExchange.
    pkg = "org.springframework.web.service.annotation" and
    superPkg = "org.springframework.web.service.annotation" and
    superName = "HttpExchange" and
    name in ["GetExchange", "PostExchange", "PutExchange", "PatchExchange", "DeleteExchange"]
  }
}
