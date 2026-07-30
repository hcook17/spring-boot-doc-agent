#!/usr/bin/env python3
"""
Unit tests for _config_keys.py's mechanical key-path extraction. Pure, no
disk I/O — mirrors the rest of this project's test-per-script convention.

Run with:
    pytest tests/test_config_keys.py -v
"""

import os
import sys
import unittest
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH
from doc_engine.scanning.support._config_keys import extract_config_keys

SCRIPT_DIR = SCRIPTS_DIR


class YamlKeyExtractionTest(unittest.TestCase):
    def test_nested_leaf_keys_get_dotted_paths(self):
        text = "spring:\n  datasource:\n    password: hunter2literal\n    url: ${DB_URL}\n"
        self.assertEqual(
            extract_config_keys(text, "application.yml"),
            ["spring.datasource.password", "spring.datasource.url"],
        )

    def test_group_headers_are_not_themselves_keys(self):
        text = "spring:\n  datasource:\n    password: x\n"
        keys = extract_config_keys(text, "application.yml")
        self.assertNotIn("spring", keys)
        self.assertNotIn("spring.datasource", keys)

    def test_sibling_groups_do_not_bleed_into_each_others_path(self):
        text = (
            "spring:\n"
            "  datasource:\n"
            "    password: a\n"
            "server:\n"
            "  port: 8080\n"
        )
        self.assertEqual(
            extract_config_keys(text, "application.yml"),
            ["server.port", "spring.datasource.password"],
        )

    def test_dedent_after_deep_nesting_pops_stack_correctly(self):
        text = (
            "a:\n"
            "  b:\n"
            "    c: 1\n"
            "  d: 2\n"  # back to a's level + 1, not a.b's child
        )
        self.assertEqual(extract_config_keys(text, "x.yml"), ["a.b.c", "a.d"])

    def test_comments_and_blank_lines_are_ignored(self):
        text = "# a comment\n\nserver:\n  # nested comment\n  port: 8080\n"
        self.assertEqual(extract_config_keys(text, "x.yml"), ["server.port"])

    def test_list_items_are_skipped_not_walked_into(self):
        text = "server:\n  hosts:\n    - a.example.com\n    - b.example.com\n  port: 8080\n"
        self.assertEqual(extract_config_keys(text, "x.yml"), ["server.port"])

    def test_quoted_keys_are_unquoted_in_output(self):
        text = '"spring.profiles.active": local\n'
        self.assertEqual(extract_config_keys(text, "x.yml"), ["spring.profiles.active"])

    def test_yaml_result_is_deduplicated_and_sorted(self):
        text = "b: 1\na: 2\n"
        self.assertEqual(extract_config_keys(text, "x.yaml"), ["a", "b"])


class PropertiesKeyExtractionTest(unittest.TestCase):
    def test_flat_dotted_keys_extracted_as_is(self):
        text = "spring.datasource.password=hunter2literal\nspring.datasource.url=${DB_URL}\n"
        self.assertEqual(
            extract_config_keys(text, "application.properties"),
            ["spring.datasource.password", "spring.datasource.url"],
        )

    def test_colon_separator_also_supported(self):
        text = "server.port: 8080\n"
        self.assertEqual(extract_config_keys(text, "application.properties"), ["server.port"])

    def test_comment_lines_ignored(self):
        text = "# a comment\n! another comment style\nserver.port=8080\n"
        self.assertEqual(extract_config_keys(text, "application.properties"), ["server.port"])


class UnsupportedFileTypeTest(unittest.TestCase):
    def test_non_yaml_non_properties_file_returns_empty(self):
        self.assertEqual(extract_config_keys("FROM openjdk:17\nENV FOO=bar\n", "Dockerfile"), [])


if __name__ == "__main__":
    unittest.main()
