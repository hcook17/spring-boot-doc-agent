#!/usr/bin/env bash
# Download the deps.txt-pinned jars from Maven Central and verify them.
#
# Two-layer provenance (see deps.txt's header for the full story):
#   1. at fetch time, the download is checked against Central's authoritative
#      .sha1 sidecar -- the bytes are what Central serves;
#   2. the file is then checked against the sha256 pin in deps.txt -- the
#      bytes are what was pinned, on every subsequent run.
# VERIFY_ONLY=1 skips the network and re-verifies lib/ against the pins.
# Any mismatch deletes the jar and fails: never compile against unverified
# bytes.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEPS="$HERE/deps.txt"
LIB="${LIB:-$HERE/lib}"
BASE_URL="${BASE_URL:-https://repo1.maven.org/maven2}"
VERIFY_ONLY="${VERIFY_ONLY:-0}"

mkdir -p "$LIB"
failed=0
count=0

while IFS=":" read -r group artifact version sha256; do
  case "${group:-}" in '' | \#*) continue ;; esac
  sha256="${sha256%$'\r'}"

  # Coordinate and digest hygiene: fixed character sets, no traversal, 64-hex.
  case "$group$artifact$version" in
    *..* | *[^A-Za-z0-9._-]*)
      echo "bad coordinate: $group:$artifact:$version" >&2
      exit 2
      ;;
  esac
  if [[ ! "$sha256" =~ ^[a-f0-9]{64}$ ]]; then
    echo "bad sha256 for $group:$artifact:$version" >&2
    exit 2
  fi

  path="${group//.//}/$artifact/$version/$artifact-$version.jar"
  jar="$LIB/$artifact-$version.jar"

  if [ "$VERIFY_ONLY" != "1" ]; then
    tmp="$jar.tmp"
    curl -fsSL "$BASE_URL/$path" -o "$tmp"
    want_sha1="$(curl -fsSL "$BASE_URL/$path.sha1")"
    got_sha1="$(sha1sum "$tmp" | cut -d' ' -f1)"
    if [ "$want_sha1" != "$got_sha1" ]; then
      echo "PROVENANCE FAIL $artifact-$version.jar: central sha1 $want_sha1, got $got_sha1" >&2
      rm -f "$tmp"
      exit 1
    fi
    mv "$tmp" "$jar"
  fi

  if [ ! -f "$jar" ]; then
    echo "MISSING $jar (run without VERIFY_ONLY first)" >&2
    failed=1
    continue
  fi
  got="$(sha256sum "$jar" | cut -d' ' -f1)"
  if [ "$got" != "$sha256" ]; then
    echo "DIGEST MISMATCH $artifact-$version.jar: pinned $sha256, got $got -- deleting" >&2
    rm -f "$jar"
    failed=1
    continue
  fi
  count=$((count + 1))
done < "$DEPS"

[ "$failed" -eq 0 ] || exit 1
echo "verified $count jar(s) against deps.txt pins"
