#!/usr/bin/env bash
# Run the spring-signals queries against a database and emit CSV, then assert.
#
#   DB            database path
#   PACKS         pack search root
#   OUT           output directory
#   CODEQL        codeql executable
#   QUERIES       space-separated query basenames (default: the wave 1 set)
#   EXPECTATIONS  JSON file of expected counts (default: none -> report only)
#
# Note on `@kind table`: these queries produce raw result tables, not alerts.
# `codeql database analyze` will NOT interpret them into SARIF -- it needs
# @kind problem/path-problem. Raw tables must go through `query run` +
# `bqrs decode`, which is what this script does. If a downstream consumer
# expects SARIF, that is a schema decision to make deliberately, not a
# side effect of query metadata.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DB="${DB:-$PWD/.codeql/ocs-api-service-db}"
PACKS="${PACKS:-$(cd "$HERE/../codeql/packs" && pwd)}"
OUT="${OUT:-$PWD/out}"
CODEQL="${CODEQL:-codeql}"
EXPECTATIONS="${EXPECTATIONS:-}"
# See create-db.sh for EXTRA_PACKS.
SEARCH_PATH="${PACKS}${EXTRA_PACKS:+:$EXTRA_PACKS}"

# Wave 1 only. References/Security/Observability/Testing still emit the legacy
# 3-column schema and are excluded on purpose. Override QUERIES to run a subset.
DEFAULT_QUERIES="ApiSurface Configuration ErrorHandling HibernateTypes JakartaMigration Messaging NativeSql OpenApiSurface OutboundClients Persistence"
read -r -a WAVE1 <<< "${QUERIES:-$DEFAULT_QUERIES}"

mkdir -p "$OUT"

# Precompile into a cache the query runs actually use. `pack create` alone wrote
# a compiled pack that the loop then ignored, recompiling from source on every
# query -- so the wall-clock term this step exists to remove was still in every
# CodeQL-vs-ast-grep timing.
"$CODEQL" pack install "$PACKS/spring-signals" --additional-packs="$SEARCH_PATH" >/dev/null
export CODEQL_COMPILATION_CACHE="${CODEQL_COMPILATION_CACHE:-$OUT/.compcache}"
mkdir -p "$CODEQL_COMPILATION_CACHE"
"$CODEQL" query compile --additional-packs="$SEARCH_PATH" \
  --compilation-cache="$CODEQL_COMPILATION_CACHE" \
  "$PACKS/spring-signals" >/dev/null

for q in "${WAVE1[@]}"; do
  echo "== $q"
  "$CODEQL" query run \
    --database="$DB" \
    --additional-packs="$SEARCH_PATH" \
    --compilation-cache="$CODEQL_COMPILATION_CACHE" \
    --output="$OUT/$q.bqrs" \
    "$PACKS/spring-signals/$q.ql" >/dev/null
  "$CODEQL" bqrs decode --format=csv --entities=string \
    "$OUT/$q.bqrs" > "$OUT/$q.csv"
  echo "   rows: $(( $(wc -l < "$OUT/$q.csv") - 1 ))"
done

echo
if [ -n "$EXPECTATIONS" ]; then
  python3 "$HERE/check-assertions.py" --out "$OUT" --expectations "$EXPECTATIONS"
else
  echo "no EXPECTATIONS file supplied; row counts reported but nothing asserted."
  echo "  pass EXPECTATIONS=harness/expectations/<repo>.json to gate on them."
fi
