#!/usr/bin/env bash
# Compile the fixture with plain javac against the pinned lib/ classpath.
#
# WHY NOT GRADLE. The only thing create-db.sh needs from a build is a javac
# invocation the CodeQL tracer can observe. Gradle would add a ~130MB
# distribution download, a daemon, and plugin resolution -- three moving parts
# that can fail for reasons unrelated to what this gate measures. javac against
# pinned coordinates is hermetic, ~2s, and reproducible. `--release 17` matches
# the toolchain ocs-api-service pins.
#
# -parameters is deliberately OMITTED: api_surface__param_binding exists to
# detect the Spring 6.1 fallback removal, and the fixture must reproduce the
# unnamed-parameter case.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -d "$HERE/lib" ] || "$HERE/fetch-deps.sh"

# Debug: print the toolchain and classpath size. This is useful when the build
# compiles locally but fails in CI because the runner resolves a different
# javac or classpath.
echo "javac: $(which javac)"
javac -version
echo "JAVA_HOME: ${JAVA_HOME:-}"
echo "classpath jars: $(find "$HERE/lib" -name '*.jar' | wc -l)"

CP="$(find "$HERE/lib" -name '*.jar' | sort | tr '\n' ':')"

# Guard against stub shadowing. Hand-written framework stubs placed under src/
# are compiled ahead of the real jars on the classpath, producing confusing
# "cannot find symbol" errors for methods that do exist in the pinned jars.
# All fixture sources must live under com/example/fixture/ so the jar types
# win on the classpath.
STRAY_FILES=$(find "$HERE/src" -type f -name '*.java' ! -path '*/src/main/java/com/example/fixture/*' ! -path '*/src/test/java/com/example/fixture/*' || true)
if [ -n "$STRAY_FILES" ]; then
  echo "ERROR: stray .java files found outside com/example/fixture/; these will shadow the downloaded jars:" >&2
  echo "$STRAY_FILES" >&2
  exit 1
fi

# Also reject any explicit stubs/ directory that contains source files.
STUB_JAVA=$(find "$HERE/src" -type d -name stubs -exec find {} -type f -name '*.java' \; 2>/dev/null || true)
if [ -n "$STUB_JAVA" ]; then
  echo "ERROR: a stubs/ directory contains .java files; these will shadow the downloaded jars:" >&2
  echo "$STUB_JAVA" >&2
  exit 1
fi

rm -rf "$HERE/build"
mkdir -p "$HERE/build/classes/main" "$HERE/build/classes/test"
find "$HERE/src/main/java" -name '*.java' > "$HERE/build/main.args"
javac --release 17 -nowarn -implicit:none -cp "$CP" -d "$HERE/build/classes/main" @"$HERE/build/main.args"
find "$HERE/src/test/java" -name '*.java' > "$HERE/build/test.args"
javac --release 17 -nowarn -implicit:none -cp "$CP:$HERE/build/classes/main" -d "$HERE/build/classes/test" @"$HERE/build/test.args"
echo "fixture compiled: $(find "$HERE/build/classes" -name '*.class' | wc -l) class files"
