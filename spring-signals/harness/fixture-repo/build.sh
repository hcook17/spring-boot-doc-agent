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
CP="$(find "$HERE/lib" -name '*.jar' | tr '\n' ':')"
rm -rf "$HERE/build"
mkdir -p "$HERE/build/classes/main" "$HERE/build/classes/test"
find "$HERE/src/main/java" -name '*.java' > "$HERE/build/main.args"
javac --release 17 -nowarn -cp "$CP" -d "$HERE/build/classes/main" @"$HERE/build/main.args"
find "$HERE/src/test/java" -name '*.java' > "$HERE/build/test.args"
javac --release 17 -nowarn -cp "$CP:$HERE/build/classes/main" -d "$HERE/build/classes/test" @"$HERE/build/test.args"
echo "fixture compiled: $(find "$HERE/build/classes" -name '*.class' | wc -l) class files"
