#!/usr/bin/env bash
# Build a CodeQL database for ocs-api-service.
#
# Why an explicit --command instead of autobuild:
#   - build.gradle sets `options.compilerArgs << "-Werror"` on BOTH compileJava
#     and compileTestJava, with Error Prone 2.10.0 wired in via net.ltgt.errorprone.
#     Autobuild picks its own task set and can miss compileTestJava entirely,
#     which silently drops all 176 test files from the database.
#   - Java toolchain is pinned to 17 in build.gradle. The CodeQL CLI's own JVM is
#     independent of the toolchain Gradle provisions; both must be present.
#   - `installGitHooks` is a dependency of compileJava and writes into .git/hooks.
#     In a detached CI checkout that task can fail; -x it there.
#
# Artifactory credentials are required to resolve com.elsevier:* dependencies.
# Extraction quality degrades badly without them: unresolved types become
# <unknown>, and every typeIsOrExtends() predicate in the pack silently
# under-matches. Verify resolution BEFORE trusting any count.
set -euo pipefail

REPO="${REPO:-$PWD}"
DB="${DB:-$PWD/.codeql/ocs-api-service-db}"
CODEQL="${CODEQL:-codeql}"

: "${artifactory_user:?set artifactory_user}"
: "${artifactory_password:?set artifactory_password}"

rm -rf "$DB"

"$CODEQL" database create "$DB" \
  --language=java \
  --source-root="$REPO" \
  --overwrite \
  --command="./gradlew --no-daemon --no-build-cache --console=plain \
      -Partifactory_user=${artifactory_user} \
      -Partifactory_password=${artifactory_password} \
      clean compileJava compileTestJava"

echo
echo "== extraction coverage sanity check =="
# Compare what CodeQL compiled against what is on disk. Any delta is a
# confound for the ast-grep/semgrep comparison and must be reconciled BEFORE
# precision/recall is computed -- CodeQL sees only what the build compiled,
# while filesystem-walking tools see everything.
DISK=$(find "$REPO/src" -name '*.java' | wc -l | tr -d ' ')
echo "on disk:    $DISK .java files under src/"
"$CODEQL" query run \
  --database="$DB" \
  --output=/tmp/files.bqrs \
  <(printf 'import java\nfrom File f where f.getExtension() = "java" select f.getRelativePath()\n') \
  >/dev/null
EXTRACTED=$("$CODEQL" bqrs decode --format=csv /tmp/files.bqrs | tail -n +2 | wc -l | tr -d ' ')
echo "extracted:  $EXTRACTED .java files"
if [ "$DISK" != "$EXTRACTED" ]; then
  echo "WARNING: extraction delta of $((DISK - EXTRACTED)) files. Reconcile before measuring."
fi
