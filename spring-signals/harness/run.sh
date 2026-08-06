#!/usr/bin/env bash
# Run the wave-1 spring-signals queries and emit CSV.
#
# Note on `@kind table`: these queries produce raw result tables, not alerts.
# `codeql database analyze` will NOT interpret them into SARIF -- it needs
# @kind problem/path-problem. Raw tables must go through `query run` +
# `bqrs decode`, which is what this script does. If a downstream consume
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
# Which expectations to grade the CSVs against. Overridable so the same script
# gates the synthetic fixture in CI (SPEC=expectations/fixture-repo.json).
SPEC="${SPEC:-$(dirname "$0")/expectations/ocs-api-service.json}"

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

# Clean, then recreate. query run refuses to overwrite an existing bqrs, so a
# rerun against a dirty OUT failed confusingly late; worse, a CSV whose query
# was removed from WAVE1 would survive into the assertion step as stale data.
# Derived output is rebuilt from scratch every run.
rm -rf "$OUT"
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

# Assertions. A query that returns zero because the library is not on the
# classpath is a valid result; a query that returns zero because it is broken
# is not. The previous loop here printed "DIFF ... <-- investigate" and still
# exited 0 -- it asserted nothing. check_assertions.py fails closed: a missing
# CSV is an error rather than zero rows, unexpected CSVs are stale-output
# errors, and any failed asserted/minimum exits 1.
echo
echo "== assertions =="
python3 "$(dirname "$0")/check_assertions.py" --spec "$SPEC" --out "$OUT"
