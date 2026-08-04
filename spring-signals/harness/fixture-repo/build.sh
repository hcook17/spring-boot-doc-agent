#!/usr/bin/env bash
# Compile the fixture with javac.
# This fixture uses local stubs for Spring/Jakarta APIs so it needs no
# Artifactory credentials or external dependency downloads.
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p build/classes/java/main
find src/main/java -name '*.java' > /tmp/java-files.txt
javac -d build/classes/java/main @/tmp/java-files.txt
