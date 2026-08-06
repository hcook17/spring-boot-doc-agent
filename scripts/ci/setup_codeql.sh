#!/usr/bin/env bash
# Bootstrap a pinned CodeQL CLI for local --actions-outage parity.
#
# Defaults match .github/workflows/ci.yml (CODEQL_BUNDLE_URL / CODEQL_SHA256)
# and .github/actions/setup-codeql: download, sha256sum -c, extract, print PATH.
#
# Usage (Linux / WSL / Git Bash with a linux64-compatible extract target):
#   bash scripts/ci/setup_codeql.sh
#   eval "$(bash scripts/ci/setup_codeql.sh --print-path-export)"
#
# Override platform bundle when not on linux64:
#   CODEQL_BUNDLE_URL=... CODEQL_SHA256=... bash scripts/ci/setup_codeql.sh
#
# Install root (default): .codeql-cli/ under the repo (gitignored locally if needed).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

# Pinned in .github/workflows/ci.yml — keep in lockstep when bumping the bundle.
CODEQL_SHA256="${CODEQL_SHA256:-cb361567fa1bdb9d322da4240f621b36f245e4d7bb97db3c3a2ad7f743c8e8e7}"
CODEQL_BUNDLE_URL="${CODEQL_BUNDLE_URL:-https://github.com/github/codeql-action/releases/download/codeql-bundle-v2.26.2/codeql-bundle-linux64.tar.gz}"
CODEQL_DIR="${CODEQL_DIR:-$REPO_ROOT/.codeql-cli}"
PRINT_EXPORT=0

for arg in "$@"; do
  case "$arg" in
    --print-path-export) PRINT_EXPORT=1 ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$CODEQL_DIR"
BUNDLE="$CODEQL_DIR/codeql-bundle.tar.gz"

if [ -x "$CODEQL_DIR/codeql" ]; then
  echo "CodeQL already present at $CODEQL_DIR/codeql" >&2
  "$CODEQL_DIR/codeql" --version >&2 || true
else
  echo "Fetching $CODEQL_BUNDLE_URL" >&2
  tmp="$BUNDLE.tmp"
  curl -fsSL --retry 5 --retry-delay 2 -o "$tmp" "$CODEQL_BUNDLE_URL"
  echo "$CODEQL_SHA256  $tmp" | sha256sum -c -
  mv "$tmp" "$BUNDLE"
  tar -xzf "$BUNDLE" -C "$CODEQL_DIR" --strip-components=1
  echo "Extracted CodeQL to $CODEQL_DIR" >&2
  "$CODEQL_DIR/codeql" --version >&2
fi

if [ "$PRINT_EXPORT" = "1" ]; then
  # stdout only — safe for eval "$(... --print-path-export)"
  printf 'export PATH=%q:$PATH\n' "$CODEQL_DIR"
else
  echo "" >&2
  echo "Add to PATH for this shell:" >&2
  printf '  export PATH=%q:$PATH\n' "$CODEQL_DIR" >&2
fi
