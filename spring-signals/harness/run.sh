#!/usr/bin/env bash
# Run the wave-1 spring-signals queries and emit CSV.
#
# Note on `@kind table`: these queries produce raw result tables, not alerts.
# `codeql database analyze` will NOT interpret them into SARIF -- it needs
# @kind problem/path-problem. Raw tables must go through `query run` +
# `bqrs decode`, which is what this script does. If a downstream consumer
# expects SARIF, that is a schema decision to make deliberately, not a
# side effect of query metadata.
#
# The pack is precompiled first. `compiled: false` in the lock file means QL
# compilation happens inside every run, which lands directly in any wall-clock
# comparison against ast-grep or semgrep. Precompiling removes that term.
set -euo pipefail

DB="${DB:-$PWD/.codeql/ocs-api-service-db}"
PACKS="${PACKS:-$PWD/codeql/packs}"
OUT="${OUT:-$PWD/out}"
CODEQL="${CODEQL:-codeql}"
EXPECTED_DIR="${EXPECTED_DIR:-$(dirname "$0")}"

# Wave 1 only. References/Security/Observability/Testing still emit the legacy
# 3-column schema and are excluded on purpose.
WAVE1=(
  ApiSurface
  Configuration
  ErrorHandling
  HibernateTypes
  JakartaMigration
  Messaging
  NativeSql
  OpenApiSurface
  OutboundClients
  Persistence
)

mkdir -p "$OUT"

"$CODEQL" pack install "$PACKS/spring-signals"
"$CODEQL" pack create  "$PACKS/spring-signals" --output="$OUT/.packcache"

for q in "${WAVE1[@]}"; do
  echo "== $q"
  "$CODEQL" query run \
    --database="$DB" \
    --additional-packs="$PACKS" \
    --output="$OUT/$q.bqrs" \
    "$PACKS/spring-signals/$q.ql"
  "$CODEQL" bqrs decode --format=csv --entities=string \
    "$OUT/$q.bqrs" > "$OUT/$q.csv"
  echo "   rows: $(( $(wc -l < "$OUT/$q.csv") - 1 ))"
done

# Row-count assertions. Empty-result checks catch queries that silently stop
# producing rows; minimum checks catch the @RestController-style regression
# where a contribution is missing and the query returns zero.
echo
echo "== row-count assertions =="
python3 "$(dirname "$0")/check-assertions.py" \
  --expected-dir "$EXPECTED_DIR" \
  --out-dir "$OUT"
