/**
 * Source-root hygiene shared by every spring-signals query.
 *
 * Restricts matches to Maven/Gradle Java source sets so generated sources
 * under build/ or target/ and arbitrary .java paths are not inventoried.
 * A source_set column is deferred (campaign Wave 2).
 */

import java

/** Holds if `e` is declared under `src/main/java` or `src/test/java`. */
predicate isJavaSource(Element e) {
  e.getFile().getRelativePath().regexpMatch("^src/(main|test)/java/.*\\.java$")
}
