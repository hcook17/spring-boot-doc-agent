"""Tests for scripts/ci/pre_pr.py — local PE pre-push orchestrator."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

import pre_pr


class ClassifyPathRiskTest(unittest.TestCase):
    def test_docs_only_is_fast(self):
        self.assertEqual(
            pre_pr.classify_path_risk(["README.md", "claude/session-log.md"]),
            "fast",
        )

    def test_scripts_change_is_standard(self):
        self.assertEqual(
            pre_pr.classify_path_risk(["scripts/ci/pre_pr.py"]),
            "standard",
        )

    def test_empty_is_standard(self):
        self.assertEqual(pre_pr.classify_path_risk([]), "standard")

    def test_github_workflow_is_standard(self):
        self.assertEqual(
            pre_pr.classify_path_risk([".github/workflows/ci.yml"]),
            "standard",
        )


class BypassTest(unittest.TestCase):
    def test_skip_without_reason_exits(self):
        with mock.patch.dict(os.environ, {"PRE_PR_SKIP": "1"}, clear=False):
            os.environ.pop("PRE_PR_SKIP_REASON", None)
            with self.assertRaises(SystemExit) as ctx:
                pre_pr.check_bypass()
            self.assertEqual(ctx.exception.code, 2)

    def test_skip_with_reason_returns_entry(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bypass_log = Path(tmp) / "pre-pr-bypass-test.log"
            with mock.patch.dict(
                os.environ,
                {"PRE_PR_SKIP": "1", "PRE_PR_SKIP_REASON": "emergency hotfix"},
                clear=False,
            ):
                with mock.patch.object(pre_pr, "BYPASS_LOG", bypass_log):
                    entry = pre_pr.check_bypass()
        self.assertIsNotNone(entry)
        self.assertEqual(entry["reason"], "emergency hotfix")


class ReceiptTest(unittest.TestCase):
    def test_write_receipt_has_required_keys(self, tmp_path_factory=None):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            receipt_path = Path(tmp) / "pre-pr-receipt.json"
            with mock.patch.object(pre_pr, "RECEIPT_PATH", receipt_path):
                receipt = pre_pr.Receipt(
                    schema_version=1,
                    git_sha="abc",
                    mode="fast",
                    suites=[
                        pre_pr.SuiteResult("ruff", "pass", 10, "hard", "exit=0"),
                    ],
                    tool_versions={"python": "3.11"},
                    overall="pass",
                )
                pre_pr.write_receipt(receipt)
            data = json.loads(receipt_path.read_text(encoding="utf-8"))
        for key in (
            "schema_version",
            "git_sha",
            "mode",
            "suites",
            "tool_versions",
            "overall",
        ):
            self.assertIn(key, data)
        self.assertEqual(data["overall"], "pass")
        self.assertEqual(data["suites"][0]["name"], "ruff")


class BuildSuitesTest(unittest.TestCase):
    def test_fast_skips_pytest(self):
        names = [n for n, _, _ in pre_pr.build_suites("fast")]
        self.assertNotIn("pytest", names)
        self.assertIn("check_repo_claims", names)
        self.assertIn("ruff", names)

    def test_standard_includes_pytest_not_stage0(self):
        names = [n for n, _, _ in pre_pr.build_suites("standard")]
        self.assertIn("pytest", names)
        self.assertNotIn("stage0_portable", names)
        self.assertNotIn("mutate_advisory", names)

    def test_full_includes_advisory_mutate(self):
        names = [n for n, _, _ in pre_pr.build_suites("full")]
        self.assertIn("pytest", names)
        self.assertIn("mutate_advisory", names)
        self.assertIn("stage0_portable", names)


class ResolveModeTest(unittest.TestCase):
    def _ns(self, *, auto=False, fast=False, full=False):
        return mock.Mock(auto=auto, fast=fast, full=full)

    def test_auto_code_diff_is_standard_not_full(self):
        with mock.patch.object(
            pre_pr,
            "changed_files_vs_main",
            return_value=["scripts/ci/pre_pr.py"],
        ):
            mode = pre_pr.resolve_mode(self._ns(auto=True))
        self.assertEqual(mode, "standard")
        self.assertNotEqual(mode, "full")

    def test_auto_docs_only_is_fast(self):
        with mock.patch.object(
            pre_pr,
            "changed_files_vs_main",
            return_value=["README.md", "claude/session-log.md"],
        ):
            mode = pre_pr.resolve_mode(self._ns(auto=True))
        self.assertEqual(mode, "fast")

    def test_no_flags_defaults_to_path_risk(self):
        with mock.patch.object(
            pre_pr,
            "changed_files_vs_main",
            return_value=["src/doc_engine/paths.py"],
        ):
            mode = pre_pr.resolve_mode(self._ns())
        self.assertEqual(mode, "standard")

    def test_full_flag_ignores_path_risk(self):
        with mock.patch.object(
            pre_pr,
            "changed_files_vs_main",
            return_value=["README.md"],
        ):
            mode = pre_pr.resolve_mode(self._ns(full=True))
        self.assertEqual(mode, "full")


class MainAutoUsesStandardSuitesTest(unittest.TestCase):
    def test_main_auto_calls_build_suites_with_standard(self):
        import tempfile

        captured: list[str] = []

        def capture_build(mode: str):
            captured.append(mode)
            return []

        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "receipt.json"
            with mock.patch.object(pre_pr, "check_bypass", return_value=None):
                with mock.patch.object(
                    pre_pr,
                    "changed_files_vs_main",
                    return_value=["scripts/ci/pre_pr.py"],
                ):
                    with mock.patch.object(
                        pre_pr, "build_suites", side_effect=capture_build
                    ):
                        with mock.patch.object(pre_pr, "RECEIPT_PATH", receipt):
                            with mock.patch.object(
                                pre_pr, "_tool_versions", return_value={}
                            ):
                                with mock.patch.object(
                                    pre_pr, "_git_sha", return_value="deadbeef"
                                ):
                                    code = pre_pr.main(["--auto"])
            self.assertEqual(code, 0)
            self.assertEqual(captured, ["standard"])
            data = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(data["mode"], "standard")
            self.assertNotEqual(data["mode"], "full")

class MainBypassTest(unittest.TestCase):
    def test_main_bypass_exits_zero(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "receipt.json"
            bypass = Path(tmp) / "bypass.log"
            with mock.patch.dict(
                os.environ,
                {"PRE_PR_SKIP": "1", "PRE_PR_SKIP_REASON": "broken hook escape"},
                clear=False,
            ):
                with mock.patch.object(pre_pr, "RECEIPT_PATH", receipt):
                    with mock.patch.object(pre_pr, "BYPASS_LOG", bypass):
                        code = pre_pr.main(["--fast"])
            self.assertEqual(code, 0)
            data = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(data["overall"], "bypassed")


if __name__ == "__main__":
    unittest.main()
