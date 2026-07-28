#!/usr/bin/env python3
"""
Unit tests for _secret_heuristics.py and check_no_secrets_leaked.py. Pure,
fast, no disk I/O beyond tiny synthetic fixtures created and torn down here
— mirrors the rest of this project's test-per-script convention.

Run with:
    python3 scripts/test_secret_heuristics.py -v
"""

import os
import shutil
import sys
import tempfile
import unittest
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

SCRIPT_DIR = SCRIPTS_DIR
import _secret_heuristics as h  # noqa: E402
import check_no_secrets_leaked as checker  # noqa: E402


class ScanTextForSecretsTest(unittest.TestCase):
    def _heuristics(self, text):
        return [hit["heuristic"] for hit in h.scan_text_for_secrets(text)]

    def test_flags_literal_password_value(self):
        hits = h.scan_text_for_secrets("password: hunter2literal\n")
        self.assertEqual(hits, [{"line": 1, "heuristic": "key-name:password"}])

    def test_does_not_flag_env_placeholder_value(self):
        self.assertEqual(self._heuristics("password: ${DB_PASSWORD}\n"), [])

    def test_does_not_flag_angle_bracket_template_value(self):
        self.assertEqual(self._heuristics("api_key: <set-me>\n"), [])

    def test_does_not_flag_changeme_placeholder(self):
        self.assertEqual(self._heuristics("client-secret: CHANGEME\n"), [])

    def test_does_not_flag_a_QUOTED_placeholder(self):
        """Found on a real build script, where every `password` line was a
        quoted `${...}` and every one was reported as a literal credential.
        PLACEHOLDER_VALUE_RE is anchored, and the line regex strips quotes
        from the key but not the value, so the quotes defeated the match.

        This matters beyond noise: agents/file-summarizer.md instructs
        subagents that the scan already excluded genuine placeholders, so
        "anything flagged is a real literal". That contract was false for
        every quoted value."""
        for line in ('password = "${DB_PASSWORD}"\n',
                     "password: '${DB_PASSWORD}'\n",
                     'api_key: "<set-me>"\n',
                     "client-secret: 'CHANGEME'\n"):
            self.assertEqual(self._heuristics(line), [], line)

    def test_a_quoted_real_secret_is_STILL_flagged(self):
        """The other direction, and the one that would matter if unquoting
        were too eager: stripping quotes must not let a literal through."""
        for line in ('password = "hunter2literal"\n',
                     "password: 'hunter2literal'\n"):
            self.assertEqual(self._heuristics(line), ["key-name:password"], line)

    def test_unbalanced_or_inner_quotes_do_not_unquote(self):
        """Only one matching surrounding pair is stripped. A value that
        merely contains a quote is left alone, so this cannot be used to
        smuggle a literal past the check."""
        self.assertEqual(self._heuristics('password: "hunter2\n'), ["key-name:password"])
        self.assertEqual(self._heuristics('password: he said "hi"\n'), ["key-name:password"])

    def test_does_not_flag_unrelated_key(self):
        self.assertEqual(self._heuristics("server:\n  port: 8080\n"), [])

    def test_flags_aws_access_key_id_regardless_of_key_name(self):
        hits = h.scan_text_for_secrets("some_random_field: AKIAABCDEFGHIJKLMNOP\n")
        self.assertIn("aws_access_key_id", [hit["heuristic"] for hit in hits])

    def test_flags_pem_private_key_block(self):
        text = "cert: |\n  -----BEGIN RSA PRIVATE KEY-----\n  abc123\n"
        hits = h.scan_text_for_secrets(text)
        self.assertTrue(any(hit["heuristic"] == "pem_private_key" for hit in hits))

    def test_line_numbers_are_one_based_and_accurate(self):
        text = "server:\n  port: 8080\npassword: literalvalue\n"
        hits = h.scan_text_for_secrets(text)
        self.assertEqual(hits, [{"line": 3, "heuristic": "key-name:password"}])

    def test_never_includes_the_matched_value_itself(self):
        secret_value = "sk_live_super_secret_value_xyz"
        hits = h.scan_text_for_secrets(f"api_key: {secret_value}\n")
        for hit in hits:
            self.assertNotIn(secret_value, str(hit))


class CheckNoSecretsLeakedTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name, content):
        path = os.path.join(self.tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_clean_output_reports_no_findings(self):
        self._write("configuration.md", "Config is supplied via environment variables.\n")
        findings = checker.check([self.tmpdir])
        self.assertEqual(findings, {})

    def test_leaked_secret_in_generated_doc_is_found(self):
        # The realistic leak vector this actually catches: doc-writer
        # reproducing a literal config snippet verbatim in a fenced code
        # block, key:value shape intact — not a secret buried mid-sentence
        # in free-text prose under an unrelated key name (e.g. "summary"),
        # which only the key-name-agnostic high-confidence patterns
        # (AWS key IDs, PEM blocks) can catch regardless of context. See
        # this module's own docstring for that stated limit.
        path = self._write(
            "configuration.md",
            "```yaml\ndatasource:\n  password: hunter2literal\n```\n",
        )
        findings = checker.check([self.tmpdir])
        self.assertIn(path, findings)

    def test_only_json_and_md_files_are_scanned(self):
        self._write("notes.txt", "password: hunter2literal\n")
        findings = checker.check([self.tmpdir])
        self.assertEqual(findings, {})

    def test_single_file_path_is_accepted_directly(self):
        path = self._write("summaries.json", '{\n  "password": "hunter2literal"\n}')
        findings = checker.check([path])
        self.assertIn(path, findings)


if __name__ == "__main__":
    unittest.main()
