#!/usr/bin/env python3
"""_build_signal_extract.py — deterministic, high-value facts from build scripts.

This module exists because ast-grep has no Groovy grammar, so a .gradle file
cannot be parsed structurally the way .java files are. The compromise is to
extract the small, stable, textually-present facts that docs need most:
plugins, dependency coordinates, Java/Spring Boot toolchain versions, and
multi-module includes. Dynamic Groovy (`project.ext`, custom DSLs, method
closures) is intentionally left out: a wrong coordinate is worse than no
coordinate.

Evidence shape matches the rest of spring_signal_scan.py:
  {file, line, match, rule_id, ...}
with typed extras where useful (plugin_id, coordinate, module,
toolchain_kind, toolchain_value). Every rule_id here is a synthetic,
heuristic rule id, not from spring_ast_grep_rules.yml, so drift-check can
re-run this extractor for tier-2 verification instead of falling back to the
"no rule_id" content-changed status.

Extraction is line-oriented and comment-aware: block comments (/* ... */)
and line comments (// ... ) are stripped from the working copy before
matching, so a dependency mentioned in a comment does not become a false
signal. This is the same citation-correctness motivation that drives the
ast-grep structural-search mandate for Java files.

Supported files:
  - build.gradle / settings.gradle / *.gradle (Groovy DSL)
  - build.gradle.kts / settings.gradle.kts / *.gradle.kts (Kotlin DSL)
  - pom.xml (Maven)
  - libs.versions.toml (Gradle version catalog)
"""

from __future__ import annotations

import re
from typing import Dict, List


def _read_text_compat(text: str) -> str:
    """Return text with a single trailing newline; input may already have one."""
    return text.rstrip("\n") + "\n"


def _strip_comments(text: str) -> str:
    """Remove Groovy/Kotlin block and line comments, preserving line numbers.

    Comments are replaced with spaces so line indices stay valid. This is
    intentionally simple: it does not handle nested block comments or string
    literals that happen to contain /*, but it is enough to avoid the common
    false-positive of a commented-out dependency becoming a signal.
    """
    # Block comments /* ... */ (non-greedy, may span lines)
    text = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), text, flags=re.DOTALL)
    # Line comments // ... (to end of line, but not inside URLs like http://)
    lines = text.splitlines(keepends=True)
    out = []
    for line in lines:
        # Find // not preceded by :
        pos = line.find("//")
        if pos >= 0 and (pos == 0 or line[pos - 1] != ":"):
            line = line[:pos] + " " * (len(line) - pos)
        out.append(line)
    return "".join(out)


def _line_number(text: str, pos: int) -> int:
    """1-based line number for character position pos in text."""
    return text.count("\n", 0, pos) + 1


def _capture_line(text: str, match: re.Match) -> int:
    """Line number of the match start, using the original (unstripped) text."""
    return text.count("\n", 0, match.start()) + 1


def _safe_match(text: str, line_no: int) -> str:
    """Return the line at line_no (1-based) from text, stripped."""
    lines = text.splitlines()
    if 1 <= line_no <= len(lines):
        return lines[line_no - 1].strip()[:200]
    return ""


# Gradle plugin declarations:
#   id 'org.springframework.boot' version '3.2.0'
#   id("org.springframework.boot") version "3.2.0"
#   apply plugin: 'org.springframework.boot'
#   plugins { id 'java' }
GRADLE_PLUGIN_RE = re.compile(
    r"(?:^|\s|\()id\s*(?:\(?\s*)['\"]([a-zA-Z0-9._\-]+)['\"]\s*\)?"
    r"(?:\s+version\s+['\"]([^'\"]+)['\"])?",
    re.MULTILINE,
)

# Same as the versioned branch above, but anchored on the trailing
# version clause so the optional version in GRADLE_PLUGIN_RE doesn't
# miss it when the id(...) form isn't used.
GRADLE_PLUGIN_VERSIONED_RE = re.compile(
    r"\bid\s*(?:\(?\s*)['\"]([a-zA-Z0-9._\-]+)['\"]\s*\)?\s+version\s+['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)

# Gradle dependency declaration: configuration 'group:name:version' or configuration "group:name:version"
# Also captures "group:name" (version omitted) and "group:name:" (empty version).
# Configurations: implementation, api, compileOnly, runtimeOnly, testImplementation, etc.
GRADLE_DEPENDENCY_RE = re.compile(
    r"\b(implementation|api|compileOnly|runtimeOnly|testImplementation|"
    r"testCompileOnly|testRuntimeOnly|compile|runtime|provided|compileClasspath|"
    r"runtimeClasspath|testCompileClasspath|testRuntimeClasspath|annotationProcessor|"
    r"developmentOnly)\s*\(?\s*['\"]([a-zA-Z0-9._\-]+)(?:\:([a-zA-Z0-9._\-]*)(?:\:([a-zA-Z0-9._\-]+))?)?['\"]\s*\)?",
    re.MULTILINE,
)

# Gradle settings include: include 'module' or include(":module")
GRADLE_INCLUDE_RE = re.compile(
    r"\binclude\s*\(?\s*['\"]([a-zA-Z0-9._\-:]+)['\"]\s*\)?",
    re.MULTILINE,
)

# Gradle toolchain / Java version:
#   sourceCompatibility = '17'
#   sourceCompatibility = JavaVersion.VERSION_17
#   java.toolchain.languageVersion = JavaLanguageVersion.of(17)
#   org.gradle.java.home=/path (gradle.properties)
GRADLE_TOOLCHAIN_RE = re.compile(
    r"\b(sourceCompatibility|targetCompatibility)\s*=\s*(?:JavaVersion\.VERSION_)?(?:JavaLanguageVersion\.of\()?\s*['\"]?([0-9._]+)['\"]?\)?",
    re.MULTILINE,
)


GRADLE_BOOT_PLUGIN_RE = re.compile(
    r"id\s*\(?\s*['\"]org\.springframework\.boot['\"]\s*\)?\s+version\s+['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)

# apply plugin: 'org.springframework.boot' does not follow the id(...) shape above.
GRADLE_APPLY_PLUGIN_RE = re.compile(
    r"apply\s+plugin\s*:\s*['\"]([a-zA-Z0-9._\-]+)['\"]",
    re.MULTILINE,
)


def _gradle_row(
    rel: str,
    text: str,
    match: re.Match[str],
    *,
    rule_id: str,
    **extra: object,
) -> Dict[str, object]:
    line = _capture_line(text, match)
    row: Dict[str, object] = {
        "file": rel,
        "line": line,
        "match": _safe_match(text, line),
        "rule_id": rule_id,
    }
    row.update(extra)
    return row


def _gradle_versioned_plugins(
    rel: str, text: str, comment_free: str,
) -> Dict[int, Dict[str, object]]:
    versioned_by_start: Dict[int, Dict[str, object]] = {}
    for match in GRADLE_PLUGIN_VERSIONED_RE.finditer(comment_free):
        versioned_by_start[match.start(1)] = _gradle_row(
            rel,
            text,
            match,
            rule_id="deployment__build_plugin",
            plugin_id=match.group(1),
            plugin_version=match.group(2),
        )
    return versioned_by_start


def _gradle_dependency_coordinate(match: re.Match[str]) -> Dict[str, str]:
    coordinate = {"group": match.group(2)}
    if match.group(3):
        coordinate["name"] = match.group(3)
    if match.group(4):
        coordinate["version"] = match.group(4)
    return coordinate


def _append_bare_gradle_plugins(
    results: List[Dict[str, object]],
    *,
    rel: str,
    text: str,
    comment_free: str,
    versioned_by_start: Dict[int, Dict[str, object]],
) -> None:
    for match in GRADLE_PLUGIN_RE.finditer(comment_free):
        if match.start(1) in versioned_by_start:
            continue
        results.append(
            _gradle_row(
                rel,
                text,
                match,
                rule_id="deployment__build_plugin",
                plugin_id=match.group(1),
                plugin_version=match.group(2) or None,
            )
        )


def _append_gradle_apply_plugins(
    results: List[Dict[str, object]],
    *,
    rel: str,
    text: str,
    comment_free: str,
) -> None:
    for match in GRADLE_APPLY_PLUGIN_RE.finditer(comment_free):
        results.append(
            _gradle_row(
                rel,
                text,
                match,
                rule_id="deployment__build_plugin",
                plugin_id=match.group(1),
                plugin_version=None,
            )
        )


def _append_gradle_dependencies(
    results: List[Dict[str, object]],
    *,
    rel: str,
    text: str,
    comment_free: str,
) -> None:
    for match in GRADLE_DEPENDENCY_RE.finditer(comment_free):
        results.append(
            _gradle_row(
                rel,
                text,
                match,
                rule_id="deployment__build_dependency",
                configuration=match.group(1),
                coordinate=_gradle_dependency_coordinate(match),
            )
        )


def _append_gradle_modules_and_toolchains(
    results: List[Dict[str, object]],
    *,
    rel: str,
    text: str,
    comment_free: str,
) -> None:
    for match in GRADLE_INCLUDE_RE.finditer(comment_free):
        results.append(
            _gradle_row(
                rel,
                text,
                match,
                rule_id="deployment__build_module",
                module=match.group(1).lstrip(":"),
            )
        )
    for match in GRADLE_TOOLCHAIN_RE.finditer(comment_free):
        results.append(
            _gradle_row(
                rel,
                text,
                match,
                rule_id="deployment__build_toolchain",
                toolchain_kind=match.group(1),
                toolchain_value=match.group(2),
            )
        )


def _extract_gradle(rel: str, text: str, comment_free: str) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    # Collect all versioned plugin ids first, then skip the bare id
    # matches that would otherwise duplicate them. We key by the position of
    # the id keyword, which is the same start position both regexes use, so
    # the bare id match for a versioned plugin is detected and suppressed.
    versioned_by_start = _gradle_versioned_plugins(rel, text, comment_free)
    results.extend(versioned_by_start.values())
    _append_bare_gradle_plugins(
        results,
        rel=rel,
        text=text,
        comment_free=comment_free,
        versioned_by_start=versioned_by_start,
    )
    _append_gradle_apply_plugins(
        results, rel=rel, text=text, comment_free=comment_free,
    )
    _append_gradle_dependencies(
        results, rel=rel, text=text, comment_free=comment_free,
    )
    _append_gradle_modules_and_toolchains(
        results, rel=rel, text=text, comment_free=comment_free,
    )
    return results


# Maven dependency: <dependency> ... <groupId>g</groupId> <artifactId>a</artifactId> <version>v</version> ... </dependency>
MAVEN_DEPENDENCY_RE = re.compile(
    r"<dependency>\s*"
    r"<groupId>([^<]+)</groupId>\s*"
    r"<artifactId>([^<]+)</artifactId>"
    r"(?:\s*<version>([^<]*)</version>)?"
    r"(?:\s*<scope>([^<]+)</scope>)?"
    r".*?"
    r"</dependency>",
    re.DOTALL,
)

# Maven plugin: <plugin> ... <groupId> ... <artifactId> ... <version> ... </plugin>
MAVEN_PLUGIN_RE = re.compile(
    r"<plugin>\s*"
    r"(?:<groupId>([^<]+)</groupId>\s*)?"
    r"<artifactId>([^<]+)</artifactId>"
    r"(?:\s*<version>([^<]*)</version>)?"
    r".*?"
    r"</plugin>",
    re.DOTALL,
)


def _maven_plugin_row(rel: str, text: str, match: re.Match[str]) -> Dict[str, object]:
    line = _capture_line(text, match)
    group = match.group(1) or "org.apache.maven.plugins"
    return {
        "file": rel,
        "line": line,
        "match": _safe_match(text, line),
        "rule_id": "deployment__build_plugin",
        "plugin_id": f"{group}:{match.group(2)}",
        "plugin_version": match.group(3) or None,
    }


def _maven_dependency_row(rel: str, text: str, match: re.Match[str]) -> Dict[str, object]:
    line = _capture_line(text, match)
    coordinate = {"group": match.group(1), "name": match.group(2)}
    if match.group(3):
        coordinate["version"] = match.group(3)
    return {
        "file": rel,
        "line": line,
        "match": _safe_match(text, line),
        "rule_id": "deployment__build_dependency",
        "configuration": match.group(4) or "compile",
        "coordinate": coordinate,
    }


def _extract_maven(rel: str, text: str) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = [
        _maven_plugin_row(rel, text, match)
        for match in MAVEN_PLUGIN_RE.finditer(text)
    ]
    results.extend(
        _maven_dependency_row(rel, text, match)
        for match in MAVEN_DEPENDENCY_RE.finditer(text)
    )
    return results


# libs.versions.toml: [versions] spring-boot = "3.2.0"
# [libraries] spring-boot-starter = { module = "org.springframework.boot:spring-boot-starter", version.ref = "spring-boot" }
VERSION_CATALOG_VERSION_RE = re.compile(
    r"^\s*([a-zA-Z0-9.\-_]+)\s*=\s*['\"]([^'\"]+)['\"]\s*$",
    re.MULTILINE,
)
VERSION_CATALOG_LIBRARY_RE = re.compile(
    r"^\s*([a-zA-Z0-9.\-_]+)\s*=\s*\{\s*"
    r"(?:module\s*=\s*['\"]([a-zA-Z0-9._\-]+):([a-zA-Z0-9._\-]+)['\"]|"
    r"group\s*=\s*['\"]([a-zA-Z0-9._\-]+)['\"].*?name\s*=\s*['\"]([a-zA-Z0-9._\-]+)['\"])"
    r".*?\}\s*$",
    re.MULTILINE | re.DOTALL,
)


def _catalog_version_row(rel: str, text: str, match: re.Match[str]) -> Dict[str, object]:
    line = _capture_line(text, match)
    return {
        "file": rel,
        "line": line,
        "match": _safe_match(text, line),
        "rule_id": "deployment__version_catalog",
        "catalog_kind": "version",
        "catalog_key": match.group(1),
        "catalog_value": match.group(2),
    }


def _catalog_library_row(
    rel: str, text: str, match: re.Match[str],
) -> Dict[str, object] | None:
    group = match.group(2) or match.group(4)
    name = match.group(3) or match.group(5)
    if not (group and name):
        return None
    line = _capture_line(text, match)
    return {
        "file": rel,
        "line": line,
        "match": _safe_match(text, line),
        "rule_id": "deployment__version_catalog",
        "catalog_kind": "library",
        "catalog_key": match.group(1),
        "coordinate": {"group": group, "name": name},
    }


def _extract_version_catalog(rel: str, text: str) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = [
        _catalog_version_row(rel, text, match)
        for match in VERSION_CATALOG_VERSION_RE.finditer(text)
    ]
    for match in VERSION_CATALOG_LIBRARY_RE.finditer(text):
        row = _catalog_library_row(rel, text, match)
        if row is not None:
            results.append(row)
    return results


_GRADLE_SUFFIXES = (".gradle", ".gradle.kts")


def extract_build_signals(rel: str, text: str) -> List[Dict[str, object]]:
    """Extract structured evidence from a build script or catalog file.

    Returns a list of evidence dicts in the same shape as the Java ast-grep
    pipeline: {file, line, match, rule_id, ...}. The caller decides which
    bucket to append to (deployment).
    """
    if not text:
        return []
    name = rel.rsplit("/", 1)[-1].lower()
    if name == "pom.xml":
        return _extract_maven(rel, text)
    if name == "libs.versions.toml":
        return _extract_version_catalog(rel, text)
    if name.endswith(_GRADLE_SUFFIXES):
        comment_free = _strip_comments(text)
        return _extract_gradle(rel, text, comment_free)
    return []
