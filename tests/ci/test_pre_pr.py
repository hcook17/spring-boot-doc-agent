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
                    schema_version=2,
                    git_sha="abc",
                    mode="actions_outage",
                    suites=[
                        pre_pr.SuiteResult("ruff", "pass", 10, "hard", "exit=0"),
                    ],
                    tool_versions={"python": "3.11"},
                    overall="pass",
                    attestation="actions_outage",
                    github_status_note="https://www.githubstatus.com/",
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
            "attestation",
            "github_status_note",
        ):
            self.assertIn(key, data)
        self.assertEqual(data["overall"], "pass")
        self.assertEqual(data["schema_version"], 2)
        self.assertEqual(data["attestation"], "actions_outage")
        self.assertEqual(data["github_status_note"], "https://www.githubstatus.com/")
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
        self.assertNotIn("codeql_invariants", names)

    def test_actions_outage_includes_codeql_and_certify(self):
        names = [n for n, _, _ in pre_pr.build_suites("actions_outage")]
        self.assertIn("stage0_portable", names)
        self.assertIn("mutate_advisory", names)
        self.assertIn("codeql_invariants", names)
        self.assertIn("codeql_compile_and_ql_tests", names)
        self.assertIn("codeql_fixture_runtime", names)
        self.assertIn("certify_scan_only", names)
        self.assertIn("certify_certified", names)


class ResolveModeTest(unittest.TestCase):
    def _ns(self, *, auto=False, fast=False, full=False, actions_outage=False):
        return mock.Mock(
            auto=auto, fast=fast, full=full, actions_outage=actions_outage
        )

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

    def test_actions_outage_flag(self):
        mode = pre_pr.resolve_mode(self._ns(actions_outage=True))
        self.assertEqual(mode, "actions_outage")


class RequireOutageToolchainTest(unittest.TestCase):
    def test_missing_codeql_fails(self):
        with mock.patch.object(pre_pr.shutil, "which", return_value=None):
            code = pre_pr.require_outage_toolchain()
        self.assertEqual(code, 1)

    def test_all_present_passes(self):
        def which(name):
            return f"/bin/{name}"

        with mock.patch.object(pre_pr.shutil, "which", side_effect=which):
            code = pre_pr.require_outage_toolchain()
        self.assertEqual(code, 0)


class MainActionsOutageTest(unittest.TestCase):
    def test_missing_toolchain_exits_before_suites(self):
        import tempfile

        captured: list[str] = []

        def capture_build(mode: str):
            captured.append(mode)
            return []

        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "receipt.json"
            with mock.patch.object(pre_pr, "require_outage_toolchain", return_value=1):
                with mock.patch.object(
                    pre_pr, "build_suites", side_effect=capture_build
                ):
                    with mock.patch.object(pre_pr, "RECEIPT_PATH", receipt):
                        code = pre_pr.main(["--actions-outage"])
        self.assertEqual(code, 1)
        self.assertEqual(captured, [])

    def test_skip_refused_under_outage(self):
        with mock.patch.dict(
            os.environ,
            {"PRE_PR_SKIP": "1", "PRE_PR_SKIP_REASON": "should not work here"},
            clear=False,
        ):
            with mock.patch.object(pre_pr, "require_outage_toolchain", return_value=0):
                code = pre_pr.main(["--actions-outage"])
        self.assertEqual(code, 2)

    def test_success_writes_attestation_receipt(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "receipt.json"

            def empty_suites(mode: str):
                self.assertEqual(mode, "actions_outage")
                return []

            env = {k: v for k, v in os.environ.items() if k not in (
                "PRE_PR_SKIP",
                "PRE_PR_SKIP_REASON",
            )}
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch.object(pre_pr, "require_outage_toolchain", return_value=0):
                    with mock.patch.object(pre_pr, "check_bypass", return_value=None):
                        with mock.patch.object(
                            pre_pr, "build_suites", side_effect=empty_suites
                        ):
                            with mock.patch.object(pre_pr, "RECEIPT_PATH", receipt):
                                with mock.patch.object(
                                    pre_pr, "_tool_versions", return_value={}
                                ):
                                    with mock.patch.object(
                                        pre_pr, "_git_sha", return_value="deadbeef"
                                    ):
                                        code = pre_pr.main(
                                            [
                                                "--actions-outage",
                                                "--status-url",
                                                "https://www.githubstatus.com/",
                                            ]
                                        )
            self.assertEqual(code, 0)
            data = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(data["mode"], "actions_outage")
            self.assertEqual(data["attestation"], "actions_outage")
            self.assertEqual(
                data["github_status_note"], "https://www.githubstatus.com/"
            )
            self.assertEqual(data["schema_version"], 2)
            self.assertEqual(data["overall"], "pass")


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
