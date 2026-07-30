#!/usr/bin/env python3
"""Contract for prompt_contracts.py, and the equality assertions it exists for.

The property defended: **the constants the Stage-1/2/3 validators enforce are
still the constants the agent prompts state.** Nothing checked that before.
`tests/doc_engine/test_pipeline_stages.py` held hand-copied duplicates of `agents/*.md`'s
`spring_role` enumeration and per-file JSON keys, so editing a prompt left the
suite green while validating the previous contract -- an agreement between two
copies of the same stale answer.

Not covered by sibling suites. `tests/doc_engine/test_pipeline_stages.py` checks that *output*
conforms to those constants; it has no opinion on whether the constants are
right. `check_repo_claims.py` reads `agents/*.md` only for the `tools:`
frontmatter line (check F). The prompt bodies were unread by any code.

The load-bearing tests are the three `..._matches_the_prompt` cases. Each is
proven non-vacuous by `PromptEditGoesRedTest`, which mangles a copy of the
prompt and asserts the parse either changes or raises -- because an equality
test between two things that never move is indistinguishable from no test.

Run with: pytest tests/ci/test_prompt_contracts.py -v
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH
from doc_engine.tools import doc_tag_utils
from doc_engine.tools import pipeline_validators as pv
import prompt_contracts as pc


class ContractsMatchTheValidatorsTest(unittest.TestCase):
    """The three assertions this module was written to make."""

    def test_spring_roles_matches_the_prompt(self) -> None:
        self.assertEqual(pc.spring_roles(), pv.VALID_SPRING_ROLES)

    def test_file_summary_keys_match_the_prompt(self) -> None:
        self.assertEqual(pc.file_summary_keys(), pv.FILE_SUMMARY_REQUIRED_KEYS)

    def test_doc_files_match_the_prompt(self) -> None:
        self.assertEqual(pc.doc_files(), doc_tag_utils.VALID_DOC_FILES)


class ParsedValuesAreSaneTest(unittest.TestCase):
    """Guards against a parser that 'succeeds' by matching the wrong thing --
    the failure mode that would make the equality tests above agree on
    nonsense."""

    def test_the_fourteen_file_set_has_fourteen_members(self) -> None:
        self.assertEqual(len(pc.doc_files()), 14)

    def test_roles_are_lowercase_single_tokens(self) -> None:
        for role in pc.spring_roles():
            self.assertRegex(role, r"^[a-z]+(-[a-z]+)*$", role)

    def test_every_registered_contract_parses(self) -> None:
        """If a parser is added to CONTRACTS and nothing calls it, this
        notices. The registry is the denominator."""
        for name, parser in pc.CONTRACTS.items():
            with self.subTest(contract=name):
                self.assertTrue(parser(), name)


class PromptEditGoesRedTest(unittest.TestCase):
    """The non-vacuity proof. Each case edits a COPY of the prompts and
    asserts the parser notices -- never the real files, so a crash here
    cannot leave the repo mutated."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(pc.AGENTS_DIR, self.tmp / "agents")
        self._real = pc.AGENTS_DIR
        pc.AGENTS_DIR = self.tmp / "agents"

    def tearDown(self) -> None:
        pc.AGENTS_DIR = self._real
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _edit(self, name: str, old: str, new: str) -> None:
        path = pc.AGENTS_DIR / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text, f"fixture drift: {old!r} not in {name}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_adding_a_role_to_the_prompt_is_detected(self) -> None:
        self._edit("file-summarizer.md", "test, other —", "test, other, scheduler —")
        self.assertIn("scheduler", pc.spring_roles())
        self.assertNotEqual(pc.spring_roles(), pv.VALID_SPRING_ROLES)

    def test_renaming_a_json_key_in_the_prompt_is_detected(self) -> None:
        self._edit("file-summarizer.md", '"group_function"', '"groupFunction"')
        self.assertNotEqual(pc.file_summary_keys(), pv.FILE_SUMMARY_REQUIRED_KEYS)

    def test_dropping_a_doc_file_from_the_prompt_is_detected(self) -> None:
        self._edit("doc-writer.md", "glossary, ", "")
        self.assertNotEqual(pc.doc_files(), doc_tag_utils.VALID_DOC_FILES)

    def test_a_reworded_role_line_raises_rather_than_returning_empty(self) -> None:
        """Silently returning an empty set would still fail the equality
        test today, but for the wrong reason and with a useless message. A
        parser that cannot find its contract must say so."""
        self._edit("file-summarizer.md", "**Spring role** — one of:", "**Spring role**:")
        with self.assertRaises(pc.ContractParseError):
            pc.spring_roles()

    def test_a_missing_prompt_file_raises(self) -> None:
        (pc.AGENTS_DIR / "file-summarizer.md").unlink()
        with self.assertRaises(pc.ContractParseError):
            pc.spring_roles()

    def test_a_second_json_block_raises(self) -> None:
        """The key parser assumes one canonical example. Two would make
        'which block is the contract' ambiguous, and guessing is worse than
        stopping."""
        path = pc.AGENTS_DIR / "file-summarizer.md"
        path.write_text(path.read_text(encoding="utf-8") + '\n```json\n[{"x": 1}]\n```\n',
                        encoding="utf-8")
        with self.assertRaises(pc.ContractParseError):
            pc.file_summary_keys()


class ExitCodeTest(unittest.TestCase):
    def test_main_exits_zero_on_the_real_prompts(self) -> None:
        self.assertEqual(pc.main([]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
