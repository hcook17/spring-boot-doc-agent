#!/usr/bin/env bash
# Build a CodeQL database from the local fixture repo and run Wave 1 queries.
# This is a thin wrapper around create-db.sh and run.sh with fixture-specific
# paths and expectations. It requires no Artifactory credentials.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

export REPO="${REPO:-$SCRIPT_DIR/fixture-repo}"
export DB="${DB:-$SCRIPT_DIR/.codeql/fixture-db}"
export CODEQL="${CODEQL:-codeql}"
export BUILD_COMMAND="${BUILD_COMMAND:-$REPO/build.sh}"
export OUT="${OUT:-$SCRIPT_DIR/out}"
export EXPECTED_DIR="${EXPECTED_DIR:-$SCRIPT_DIR/fixture-expected}"

"$SCRIPT_DIR/create-db.sh"

# Clean previous query output so stale CSVs are not re-checked.
rm -rf "$OUT"

export PACKS="${PACKS:-$SCRIPT_DIR/../codeql/packs}"
"$SCRIPT_DIR/run.sh"
