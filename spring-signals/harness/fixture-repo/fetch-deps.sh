#!/usr/bin/env bash
# Download the pinned compile-time classpath into lib/ from Maven Central and
# verify every artifact against the sha256 recorded in deps.txt.
#
# No Artifactory, no credentials, no Gradle distribution. Idempotent: an
# artifact already present and matching its digest is not re-fetched.
#
# The digest is what makes this fixture a fixture. Without it the "same" build
# can silently change under you when a repository mirror serves a different
# byte stream, and every count this harness asserts would move with it. A
# version range would be worse still -- see the missing codeql-pack.lock.yml
# for the same failure one layer up.
#
#   MAVEN_REPO_URL   override the mirror (default: Maven Central)
#   VERIFY_ONLY=1    check existing jars and exit; download nothing
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_URL="${MAVEN_REPO_URL:-https://repo.maven.apache.org/maven2}"
VERIFY_ONLY="${VERIFY_ONLY:-0}"
mkdir -p "$HERE/lib"

fail=0
count=0
while read -r line; do
  line="${line%%#*}"
  [ -z "${line// }" ] && continue
  coord="$(echo "$line" | awk '{print $1}')"
  want="$(echo "$line" | awk '{print $2}')"
  g="${coord%%:*}"; rest="${coord#*:}"; a="${rest%%:*}"; v="${rest##*:}"
  # The coordinate becomes a filename and a URL path segment; reject anything
  # that could escape lib/ or smuggle a path.
  case "$g$a$v" in
    *[!A-Za-z0-9._-]*|*..*)
      echo "ERROR: unsafe coordinate in deps.txt: $coord" >&2
      exit 1
      ;;
    *) ;;
  esac
  jar="$HERE/lib/$a-$v.jar"
  count=$((count + 1))

  if [ ! -f "$jar" ]; then
    if [ "$VERIFY_ONLY" = "1" ]; then
      echo "  MISSING $a-$v.jar"; fail=1; continue
    fi
    url="$REPO_URL/$(echo "$g" | tr '.' '/')/$a/$v/$a-$v.jar"
    echo "  fetch $a-$v.jar"
    tmp="$jar.tmp"
    curl -fsSL --retry 5 --retry-delay 2 --retry-connrefused \
      "$url" -o "$tmp" || { rm -f "$tmp"; exit 1; }
    mv "$tmp" "$jar"
  fi

  if [ -n "$want" ]; then
    got="$(sha256sum "$jar" | awk '{print $1}')"
    if [ "$got" != "$want" ]; then
      echo "  DIGEST MISMATCH $a-$v.jar"
      echo "    expected $want"
      echo "    got      $got"
      # Remove the bad jar: leaving it would make every later run fail the
      # same digest check without re-fetching, which reads as a permanent
      # mismatch rather than a one-off bad download.
      if [ "$VERIFY_ONLY" != "1" ]; then rm -f "$jar"; fi
      fail=1
    fi
  else
    echo "  WARNING: no sha256 pinned for $coord"
  fi
done < "$HERE/deps.txt"

if [ "$fail" != "0" ]; then
  echo "classpath verification FAILED" >&2
  exit 1
fi
echo "classpath: $count jars verified in $HERE/lib"
