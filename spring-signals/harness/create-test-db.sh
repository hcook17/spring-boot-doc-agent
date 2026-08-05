#!/usr/bin/env bash
# One-command local runtime gate. No Artifactory, no credentials, no Gradle.
#
#   ./harness/create-test-db.sh
#
# Fetches the pinned fixture classpath, compiles the fixture with javac, builds
# a CodeQL database from that traced build, runs the wave-1 queries, and asserts
# against harness/expectations/fixture-repo.json.
#
# This is the gate that was missing while items 2-4 were described as "blocked
# on CodeQL CLI + Artifactory". Only the ocs DATABASE needs Artifactory; the
# CLI, the pack dependencies, and this fixture do not.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FIXTURE="$HERE/fixture-repo"
CODEQL="${CODEQL:-codeql}"
PACKS="${PACKS:-$(cd "$HERE/../codeql/packs" && pwd)}"
DB="${DB:-$HERE/.codeql/fixture-db}"
OUT="${OUT:-$HERE/out-fixture}"
EXTRA_PACKS="${EXTRA_PACKS:-}"

# Pre-flight: fail fast if the CodeQL CLI is missing, before spending time on
# dependency downloads.
if ! command -v "$CODEQL" >/dev/null 2>&1; then
  echo "ERROR: codeql not found on PATH: $CODEQL" >&2
  exit 1
fi

for script in "$FIXTURE/fetch-deps.sh" "$FIXTURE/build.sh" "$HERE/create-db.sh" "$HERE/run.sh"; do
  if [ ! -x "$script" ]; then
    echo "ERROR: not executable: $script" >&2
    exit 1
  fi
done

"$FIXTURE/fetch-deps.sh"

REPO="$FIXTURE" \
BUILD_COMMAND="$FIXTURE/build.sh" \
SOURCE_DIR="src" \
CODEQL="$CODEQL" \
PACKS="$PACKS" \
DB="$DB" \
EXTRA_PACKS="$EXTRA_PACKS" \
"$HERE/create-db.sh"

QUERIES="${QUERIES:-}" \
EXPECTATIONS="${EXPECTATIONS:-$HERE/expectations/fixture-repo.json}" \
CODEQL="$CODEQL" \
PACKS="$PACKS" \
DB="$DB" \
OUT="$OUT" \
EXTRA_PACKS="$EXTRA_PACKS" \
"$HERE/run.sh"
