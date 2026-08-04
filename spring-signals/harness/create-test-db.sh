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
export CODEQL="${CODEQL:-codeql}"
export PACKS="${PACKS:-$(cd "$HERE/../codeql/packs" && pwd)}"
export DB="${DB:-$HERE/.codeql/fixture-db}"
export OUT="${OUT:-$HERE/out-fixture}"
export EXTRA_PACKS="${EXTRA_PACKS:-}"

"$FIXTURE/fetch-deps.sh"

REPO="$FIXTURE" \
BUILD_COMMAND="$FIXTURE/build.sh" \
SOURCE_DIR="src" \
"$HERE/create-db.sh"

QUERIES="${QUERIES:-}" \
EXPECTATIONS="${EXPECTATIONS:-$HERE/expectations/fixture-repo.json}" \
"$HERE/run.sh"
