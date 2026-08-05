#!/usr/bin/env bash
# Build a CodeQL database for a Java repository.
#
# Defaults target ocs-api-service and therefore need Artifactory credentials.
# Every input is overridable so the same script builds a database for the
# credential-free fixture in harness/fixture-repo (see create-test-db.sh).
#
#   REPO            source root to extract              (default: $PWD)
#   BUILD_COMMAND   command CodeQL traces               (default: the ocs gradle build)
#   DB              database output path
#   CODEQL          codeql executable
#   SOURCE_DIR      subdirectory counted for the extraction check (default: src)
#   PACKS           pack search root, for the coverage query
#   STRICT_EXTRACTION  1 (default) = a nonzero delta fails the build
#
# Why an explicit --command instead of autobuild, for the ocs default:
#   - build.gradle sets `options.compilerArgs << "-Werror"` on BOTH compileJava
#     and compileTestJava, with Error Prone 2.10.0 wired in via net.ltgt.errorprone.
#     Autobuild picks its own task set and can miss compileTestJava entirely,
#     which silently drops the test sources from the database.
#   - Java toolchain is pinned to 17 in build.gradle. The CodeQL CLI's own JVM is
#     independent of the toolchain Gradle provisions; both must be present.
#   - `installGitHooks` is a dependency of compileJava and writes into .git/hooks.
#     In a detached CI checkout that task can fail; -x it there.
#
# Artifactory credentials are required to resolve com.elsevier:* dependencies.
# Extraction quality degrades badly without them: unresolved types become
# <unknown>, and every typeIsOrExtends() predicate in the pack silently
# under-matches. Verify resolution BEFORE trusting any count.
#
# Credentials are passed through the ENVIRONMENT, not through --command.
# Interpolating a password into the traced command line puts it in `ps` output
# and in the build log CodeQL writes inside the database directory.
# Gradle reads ORG_GRADLE_PROJECT_<name> as project property <name>.
set -euo pipefail

REPO="${REPO:-$PWD}"
DB="${DB:-$PWD/.codeql/ocs-api-service-db}"
CODEQL="${CODEQL:-codeql}"
SOURCE_DIR="${SOURCE_DIR:-src}"
PACKS="${PACKS:-$(cd "$(dirname "$0")/../codeql/packs" && pwd)}"
STRICT_EXTRACTION="${STRICT_EXTRACTION:-1}"

if ! command -v "$CODEQL" >/dev/null 2>&1; then
  echo "ERROR: codeql not found on PATH: $CODEQL" >&2
  exit 1
fi
# EXTRA_PACKS lets an offline/air-gapped checkout point at a pre-populated
# codeql/java-all tree instead of resolving it from ghcr.io at run time.
SEARCH_PATH="${PACKS}${EXTRA_PACKS:+:$EXTRA_PACKS}"

DEFAULT_BUILD_COMMAND="./gradlew --no-daemon --no-build-cache --console=plain clean compileJava compileTestJava"
BUILD_COMMAND="${BUILD_COMMAND:-$DEFAULT_BUILD_COMMAND}"

# Credentials are a precondition only for the default (ocs) build.
if [ "$BUILD_COMMAND" = "$DEFAULT_BUILD_COMMAND" ]; then
  : "${artifactory_user:?set artifactory_user (or override BUILD_COMMAND for a credential-free repo)}"
  : "${artifactory_password:?set artifactory_password (or override BUILD_COMMAND for a credential-free repo)}"
  export ORG_GRADLE_PROJECT_artifactory_user="$artifactory_user"
  export ORG_GRADLE_PROJECT_artifactory_password="$artifactory_password"
fi

echo "== building database =="
echo "repo:    $REPO"
echo "db:      $DB"
echo "command: $BUILD_COMMAND"

rm -rf "$DB"
mkdir -p "$(dirname "$DB")"
( cd "$REPO" && exec "$CODEQL" database create "$DB" \
    --language=java \
    --source-root="$REPO" \
    --overwrite \
    --command="$BUILD_COMMAND" )

echo
echo "== extraction coverage sanity check =="
# Compare what CodeQL compiled against what is on disk. Any delta is a confound
# for the ast-grep/semgrep comparison and must be reconciled BEFORE precision or
# recall is computed -- CodeQL sees only what the build compiled, while
# filesystem-walking tools see everything.
#
# Both sides must count the SAME population. The previous version compared
# `find $REPO/src` against every .java file in the database, including library
# sources with no relative path, so the delta was uninterpretable in both
# directions. It also only echoed a WARNING, so "extraction delta 0" could never
# fail a run that listed it as an exit criterion.
if [ ! -d "$REPO/$SOURCE_DIR" ]; then
  echo "no $REPO/$SOURCE_DIR; skipping coverage check"
  exit 0
fi

DISK=$(cd "$REPO" && find "$SOURCE_DIR" -name '*.java' | sed 's#^\./##' | sort -u | wc -l | tr -d ' ')
"$CODEQL" query run \
  --database="$DB" \
  --additional-packs="$SEARCH_PATH" \
  --output="$DB.coverage.bqrs" \
  "$PACKS/spring-signals/Coverage.ql" >/dev/null
EXTRACTED=$("$CODEQL" bqrs decode --format=csv --no-titles "$DB.coverage.bqrs" \
  | sed 's/^"//; s/"$//; s#^\./##' | sort -u | wc -l | tr -d ' ')

echo "on disk:    $DISK .java files under $SOURCE_DIR/"
echo "extracted:  $EXTRACTED .java files in a recognised source set"
if [ "$DISK" != "$EXTRACTED" ]; then
  echo "EXTRACTION DELTA: $((DISK - EXTRACTED)) file(s) on disk were not extracted."
  echo "  Reconcile before measuring. Set STRICT_EXTRACTION=0 to downgrade to a warning."
  if [ "$STRICT_EXTRACTION" = "1" ]; then exit 1; fi
else
  echo "extraction delta 0"
fi
