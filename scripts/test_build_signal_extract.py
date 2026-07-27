#!/usr/bin/env python3
"""Unit tests for _build_signal_extract.py.

No ast-grep required; these are pure string tests against the same extractor
spring_signal_scan.py calls.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _build_signal_extract as bse  # noqa: E402


class GradlePluginTest(unittest.TestCase):
    def test_groovy_plugin_with_version(self):
        text = "plugins {\n    id 'org.springframework.boot' version '3.2.0'\n    id 'java'\n}"
        rows = bse.extract_build_signals("build.gradle", text)
        plugins = [r for r in rows if r["rule_id"] == "deployment__build_plugin"]
        self.assertEqual(len(plugins), 2)
        self.assertEqual(plugins[0]["plugin_id"], "org.springframework.boot")
        self.assertEqual(plugins[0]["plugin_version"], "3.2.0")
        self.assertEqual(plugins[1]["plugin_id"], "java")
        self.assertIsNone(plugins[1]["plugin_version"])

    def test_kotlin_plugin_with_version(self):
        text = 'plugins {\n    id("org.springframework.boot") version "3.2.0"\n}'
        rows = bse.extract_build_signals("build.gradle.kts", text)
        plugins = [r for r in rows if r["rule_id"] == "deployment__build_plugin"]
        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0]["plugin_id"], "org.springframework.boot")
        self.assertEqual(plugins[0]["plugin_version"], "3.2.0")

    def test_apply_plugin(self):
        text = "apply plugin: 'org.springframework.boot'\n"
        rows = bse.extract_build_signals("build.gradle", text)
        plugins = [r for r in rows if r["rule_id"] == "deployment__build_plugin"]
        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0]["plugin_id"], "org.springframework.boot")


class GradleDependencyTest(unittest.TestCase):
    def test_groovy_dependency(self):
        text = "dependencies {\n    implementation 'org.springframework.boot:spring-boot-starter-web:3.2.0'\n}"
        rows = bse.extract_build_signals("build.gradle", text)
        deps = [r for r in rows if r["rule_id"] == "deployment__build_dependency"]
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]["configuration"], "implementation")
        self.assertEqual(deps[0]["coordinate"], {"group": "org.springframework.boot",
                                                  "name": "spring-boot-starter-web",
                                                  "version": "3.2.0"})

    def test_kotlin_dependency_no_version(self):
        text = 'dependencies {\n    implementation("org.springframework.boot:spring-boot-starter-web")\n}'
        rows = bse.extract_build_signals("build.gradle.kts", text)
        deps = [r for r in rows if r["rule_id"] == "deployment__build_dependency"]
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]["configuration"], "implementation")
        self.assertEqual(deps[0]["coordinate"], {"group": "org.springframework.boot",
                                                  "name": "spring-boot-starter-web"})

    def test_dependency_in_comment_ignored(self):
        text = "dependencies {\n    // implementation 'com.example:secret:1.0'\n}"
        rows = bse.extract_build_signals("build.gradle", text)
        deps = [r for r in rows if r["rule_id"] == "deployment__build_dependency"]
        self.assertEqual(deps, [])

    def test_dependency_in_block_comment_ignored(self):
        text = "dependencies {\n    /* implementation 'com.example:block:1.0' */\n}"
        rows = bse.extract_build_signals("build.gradle", text)
        deps = [r for r in rows if r["rule_id"] == "deployment__build_dependency"]
        self.assertEqual(deps, [])


class GradleModuleTest(unittest.TestCase):
    def test_include(self):
        text = "include 'billing'\ninclude(':ledger')\n"
        rows = bse.extract_build_signals("settings.gradle", text)
        mods = [r for r in rows if r["rule_id"] == "deployment__build_module"]
        self.assertEqual({m["module"] for m in mods}, {"billing", "ledger"})


class GradleToolchainTest(unittest.TestCase):
    def test_source_compatibility(self):
        text = "sourceCompatibility = '17'\n"
        rows = bse.extract_build_signals("build.gradle", text)
        tcs = [r for r in rows if r["rule_id"] == "deployment__build_toolchain"]
        self.assertEqual(len(tcs), 1)
        self.assertEqual(tcs[0]["toolchain_kind"], "sourceCompatibility")
        self.assertEqual(tcs[0]["toolchain_value"], "17")


class MavenTest(unittest.TestCase):
    def test_maven_dependency(self):
        text = ("<dependencies>\n"
                "<dependency>\n<groupId>org.springframework.boot</groupId>\n"
                "<artifactId>spring-boot-starter</artifactId>\n<version>3.2.0</version>\n"
                "<scope>compile</scope>\n</dependency>\n</dependencies>")
        rows = bse.extract_build_signals("pom.xml", text)
        deps = [r for r in rows if r["rule_id"] == "deployment__build_dependency"]
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]["configuration"], "compile")
        self.assertEqual(deps[0]["coordinate"], {"group": "org.springframework.boot",
                                                  "name": "spring-boot-starter",
                                                  "version": "3.2.0"})

    def test_maven_plugin(self):
        text = ("<build>\n<plugins>\n<plugin>\n"
                "<groupId>org.springframework.boot</groupId>\n<artifactId>spring-boot-maven-plugin</artifactId>\n"
                "<version>3.2.0</version>\n</plugin>\n</plugins>\n</build>")
        rows = bse.extract_build_signals("pom.xml", text)
        plugins = [r for r in rows if r["rule_id"] == "deployment__build_plugin"]
        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0]["plugin_id"], "org.springframework.boot:spring-boot-maven-plugin")


class VersionCatalogTest(unittest.TestCase):
    def test_catalog_version_and_library(self):
        text = ("[versions]\n"
                "spring-boot = \"3.2.0\"\n"
                "[libraries]\n"
                "spring-boot-starter = { module = \"org.springframework.boot:spring-boot-starter\", version.ref = \"spring-boot\" }\n")
        rows = bse.extract_build_signals("libs.versions.toml", text)
        versions = [r for r in rows if r["rule_id"] == "deployment__version_catalog" and r["catalog_kind"] == "version"]
        libs = [r for r in rows if r["rule_id"] == "deployment__version_catalog" and r["catalog_kind"] == "library"]
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["catalog_key"], "spring-boot")
        self.assertEqual(len(libs), 1)
        self.assertEqual(libs[0]["catalog_key"], "spring-boot-starter")


if __name__ == "__main__":
    unittest.main()
