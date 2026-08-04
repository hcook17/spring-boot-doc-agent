#!/usr/bin/env bash
# Build a CodeQL database for a Java repository.
#
# Default mode: ocs-api-service @ develop.
#   Requires Artifactory credentials because the build resolves com.elsevier:*
#   dependencies. Extraction quality degrades badly without them: unresolved types
#   become <unknown>, and every typeIsOrExtends() predicate in the pack silently
#   under-matches. Verify resolution BEFORE trusting any count.
#
# Local-fixture mode: set REPO and BUILD_COMMAND to point at a self-contained
# repository that does not need Artifactory. For example:
#   REPO=./fixture-repo BUILD_COMMAND="./gradlew --no-daemon compileJava" ./create-db.sh
#   REPO=./fixture-repo BUILD_COMMAND="mvn -q compile" ./create-db.sh
#   REPO=./fixture-repo BUILD_COMMAND="javac -d build/classes/java/main $(find src -name '*.java')" ./create-db.sh
#
# Why an explicit --command instead of autobuild:
#   - build.gradle may set `options.compilerArgs << "-Werror"` on compileJava
#     and compileTestJava. Autobuild picks its own task set and can miss
#     compileTestJava entirely, which silently drops test files from the DB.
#   - The CodeQL CLI's own JVM is independent of the toolchain Gradle
#     provisions; both must be present.
#   - `installGitHooks` may be a dependency of compileJava and write into
#     .git/hooks; in a detached checkout that task can fail and should be -x'd.
#
set -euo pipefail

REPO="${REPO:-$PWD}"
DB="${DB:-$PWD/.codeql/ocs-api-service-db}"
CODEQL="${CODEQL:-codeql}"

# Default build command for ocs-api-service. Requires Artifactory credentials.
DEFAULT_BUILD_COMMAND="./gradlew --no-daemon --no-build-cache --console=plain \
    clean compileJava compileTestJava"
BUILD_COMMAND="${BUILD_COMMAND:-$DEFAULT_BUILD_COMMAND}"

# Artifactory credentials are only required for the default ocs-api-service build.
# A local fixture that sets BUILD_COMMAND does not need them.
if [ "$BUILD_COMMAND" = "$DEFAULT_BUILD_COMMAND" ]; then
  : "${artifactory_user:?set artifactory_user}"
  : "${artifactory_password:?set artifactory_password}"

  # Pass credentials via ORG_GRADLE_PROJECT_* so they are never visible in the
  # Gradle command line or in CodeQL build logs inside the database artifact.
  export ORG_GRADLE_PROJECT_artifactory_user="$artifactory_user"
  export ORG_GRADLE_PROJECT_artifactory_password="$artifactory_password"
fi

mkdir -p "$(dirname "$DB")"
rm -rf "$DB"

# Run the build from the repository root so relative paths in the build command
# resolve correctly. CodeQL's --source-root controls what is indexed.
(
  cd "$REPO"
  "$CODEQL" database create "$DB" \
    --language=java \
    --source-root="$REPO" \
    --overwrite \
    --command="$BUILD_COMMAND"
)

echo
echo "== extraction coverage sanity check =="
# Compare what CodeQL compiled against what is on disk. Any delta is a
# confound for the ast-grep/semgrep comparison and must be reconciled BEFORE
# precision/recall is computed -- CodeQL sees only what the build compiled,
# while filesystem-walking tools see everything.
DISK=$(find "$REPO/src" -name '*.java' 2>/dev/null | wc -l | tr -d ' ')
echo "on disk:    $DISK .java files under src/"
EXTRACTED=$(unzip -l "$DB/src.zip" 2>/dev/null | grep '\.java$' | wc -l | tr -d ' ')
echo "extracted:  $EXTRACTED .java files"
if [ "$DISK" != "$EXTRACTED" ]; then
  echo "ERROR: extraction delta of $((DISK - EXTRACTED)) files. Reconcile before measuring." >&2
  exit 1
fi
