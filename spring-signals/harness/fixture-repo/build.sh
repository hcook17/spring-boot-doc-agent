#!/usr/bin/env bash
# Compile the fixture against the verified jars in lib/.
#
# Derived output (classes/) is rebuilt from scratch every run -- the same
# idempotence discipline as run.sh, so a removed source can never leave a
# stale .class behind. Run fetch-deps.sh first; this script refuses to
# compile against an empty lib rather than producing a silently degraded
# database (unresolved types become <unknown> and every typeIsOrExtends
# predicate under-matches -- see create-db.sh's header).
#
# Portability: javac is a native binary, so on MSYS/Git Bash the classpath
# must go through cygpath (-cp is not rewritten by the shell's argument
# translation, and an @argfile is read by javac itself, never by the shell).
# Sources are passed relative to $SRC, which needs no translation anywhere.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LIB="$HERE/lib"
OUT="$HERE/classes"
SRC="$HERE/src/main/java"

shopt -s nullglob
jars=("$LIB"/*.jar)
if [ "${#jars[@]}" -eq 0 ]; then
  echo "no jars in $LIB -- run fetch-deps.sh first" >&2
  exit 2
fi
CP="$(IFS=:; echo "${jars[*]}")"

HOST_CP="$CP"
HOST_OUT="$OUT"
if command -v cygpath >/dev/null 2>&1; then
  HOST_CP="$(cygpath -mp "$CP")"
  HOST_OUT="$(cygpath -m "$OUT")"
fi

rm -rf "$OUT"
mkdir -p "$OUT"

cd "$SRC"
mapfile -t sources < <(find . -name '*.java' | sort)
javac --release 17 -cp "$HOST_CP" -d "$HOST_OUT" "${sources[@]}"
echo "compiled $(find "$OUT" -name '*.class' | wc -l) classes from ${#sources[@]} sources"
