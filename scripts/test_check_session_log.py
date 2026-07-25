#!/usr/bin/env python3
"""
Unit tests for check_session_log.py.

No live git calls — the resolved-SHA set is injected, same split
test_check_llms_coverage.py draws against its own live `gh` calls. The one
exception is RealCorpusTest at the bottom, which runs the checker over the
actual claude/session-log/ and claude/tool-quirks/ directories; it skips
cleanly when they don't exist yet, so this file can land before the split.

Several tests are regressions against specific real entries rather than
hypotheticals — the indented `Files touched:` label, the entry with four
untagged bullets, the inline "none needed beyond ..." diagnostic value, and
above all AnchorCoverageTest, which exists because a tag regex that matches
nothing reports as a clean corpus rather than as a broken check.

Run with:
    python3 scripts/test_check_session_log.py -v
"""

import io
import os
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import check_session_log as c  # noqa: E402

EM = c.EM_DASH

SESSION_FM = {
    "team": "platform",
    "epic": "repo-hygiene",
    "ticket": "UNASSIGNED-NO-TRACKER",
    "pr": "31",
    "session": "1",
    "date": "2026-07-24",
}

QUIRK_FM = {
    "team": "platform",
    "epic": "tool-quirks",
    "ticket": "UNASSIGNED-NO-TRACKER",
    "kind": "gh-cli",
    "session": "1",
    "date": "2026-07-24",
}

SESSION_BODY = f"""\
## 2026-07-24 {EM} Do a thing
Commit: abc1234
Tests: 236 passing
Assumptions affected:
- `claude/steering-prompts/00-shared-research-standards.md` {EM} "a quote" {EM} [Resolved {EM} did it]
Files touched: scripts/x.py
"""

QUIRK_BODY = f"""\
## 2026-07-24 {EM} A tool did something odd
Tools/commands involved: gh CLI 2.96.0
Status: [Unresolved {EM} needs research]
Symptom: it reported success while the real state differed
Diagnostic steps taken (re-runnable):
    gh --version
Resolution / workaround: none yet
"""


def build(frontmatter, body):
    lines = ["---"]
    lines += [f"{k}: {v}" for k, v in frontmatter.items()]
    lines += ["---"]
    return "\n".join(lines) + "\n" + body


def write_entry(kind, name="2026-07-24-do-a-thing.md", frontmatter=None, body=None, text=None):
    """Writes one entry to a fresh temp dir and returns the parsed Entry."""
    if kind == c.SESSION_LOG:
        frontmatter = SESSION_FM if frontmatter is None else frontmatter
        body = SESSION_BODY if body is None else body
    else:
        frontmatter = QUIRK_FM if frontmatter is None else frontmatter
        body = QUIRK_BODY if body is None else body
    d = pathlib.Path(tempfile.mkdtemp())
    path = d / name
    path.write_text(build(frontmatter, body) if text is None else text, encoding="utf-8")
    return c.parse_entry(path, kind)


def issues_for(kind, **kwargs):
    issues, _ = c.check_entry(write_entry(kind, **kwargs))
    return issues


def warnings_for(kind, **kwargs):
    _, warnings = c.check_entry(write_entry(kind, **kwargs))
    return warnings


def fm_with(base, **overrides):
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


class CleanEntryTest(unittest.TestCase):
    def test_session_log_entry_is_clean(self):
        self.assertEqual(issues_for(c.SESSION_LOG), [])

    def test_tool_quirks_entry_is_clean(self):
        self.assertEqual(issues_for(c.TOOL_QUIRKS), [])


class FilenameTest(unittest.TestCase):
    def test_uppercase_rejected(self):
        found = issues_for(c.SESSION_LOG, name="2026-07-24-Do-A-Thing.md")
        self.assertTrue(any("filename" in i for i in found))

    def test_underscores_rejected(self):
        found = issues_for(c.SESSION_LOG, name="2026-07-24-do_a_thing.md")
        self.assertTrue(any("filename" in i for i in found))

    def test_missing_date_prefix_rejected(self):
        found = issues_for(c.SESSION_LOG, name="do-a-thing.md")
        self.assertTrue(any("filename" in i for i in found))


class FrontmatterTest(unittest.TestCase):
    def test_no_frontmatter_flagged(self):
        found = issues_for(c.SESSION_LOG, text=SESSION_BODY)
        self.assertTrue(any("no parseable frontmatter" in i for i in found))

    def test_each_missing_key_flagged(self):
        for key in SESSION_FM:
            with self.subTest(key=key):
                found = issues_for(c.SESSION_LOG, frontmatter=fm_with(SESSION_FM, **{key: None}))
                self.assertTrue(any(f"missing required key `{key}:`" in i for i in found))

    def test_unrecognized_key_flagged(self):
        # The realistic typo: `tickets:` sitting next to `ticket:`.
        found = issues_for(c.SESSION_LOG, frontmatter=fm_with(SESSION_FM, tickets="ABC-1"))
        self.assertTrue(any("unrecognized key `tickets:`" in i for i in found))

    def test_ticket_accepts_id_and_sentinels(self):
        for value in ("PLAT-412",) + c.TICKET_SENTINELS:
            with self.subTest(value=value):
                found = issues_for(c.SESSION_LOG, frontmatter=fm_with(SESSION_FM, ticket=value))
                self.assertEqual(found, [])

    def test_ticket_rejects_bare_null(self):
        # `null` is exactly what the sentinel set exists to replace.
        found = issues_for(c.SESSION_LOG, frontmatter=fm_with(SESSION_FM, ticket="null"))
        self.assertTrue(any("ticket: null" in i for i in found))

    def test_pr_accepts_number_and_sentinels(self):
        for value in ("31",) + c.PR_SENTINELS:
            with self.subTest(value=value):
                found = issues_for(c.SESSION_LOG, frontmatter=fm_with(SESSION_FM, pr=value))
                self.assertEqual(found, [])

    def test_unknown_epic_is_an_issue_not_a_warning(self):
        found = issues_for(c.SESSION_LOG, frontmatter=fm_with(SESSION_FM, epic="typoed-epic"))
        self.assertTrue(any("epic: typoed-epic" in i for i in found))

    def test_pr_in_tool_quirks_is_an_unrecognized_key(self):
        # tool-quirks entries are PR-less by nature, so `pr:` isn't in its schema.
        found = issues_for(c.TOOL_QUIRKS, frontmatter=fm_with(QUIRK_FM, pr="31"))
        self.assertTrue(any("unrecognized key `pr:`" in i for i in found))

    def test_bad_date_format_flagged(self):
        found = issues_for(
            c.SESSION_LOG,
            name="2026-7-24-do-a-thing.md",
            frontmatter=fm_with(SESSION_FM, date="2026-7-24"),
        )
        self.assertTrue(any("not YYYY-MM-DD" in i for i in found))


class KindVocabularyTest(unittest.TestCase):
    """kind: is the one deliberately soft field — the vocabulary was fitted to
    six historical entries and is explicitly provisional."""

    def test_every_declared_kind_is_clean(self):
        for kind_value in c.KINDS:
            with self.subTest(kind=kind_value):
                self.assertEqual(
                    issues_for(c.TOOL_QUIRKS, frontmatter=fm_with(QUIRK_FM, kind=kind_value)), []
                )

    def test_sandbox_env_is_declared(self):
        # The seventh value, earned by the first genuinely new post-split entry.
        self.assertIn("sandbox-env", c.KINDS)

    def test_unknown_kind_warns_and_is_not_an_issue(self):
        entry = write_entry(c.TOOL_QUIRKS, frontmatter=fm_with(QUIRK_FM, kind="brand-new"))
        issues, warnings = c.check_entry(entry)
        self.assertEqual(issues, [])
        self.assertTrue(any("kind: brand-new" in w for w in warnings))

    def test_unknown_kind_does_not_fail_the_build(self):
        entry = write_entry(c.TOOL_QUIRKS, frontmatter=fm_with(QUIRK_FM, kind="brand-new"))
        issues, _ = c.check_entry(entry)
        self.assertEqual(c.exit_code(issues), 0)


class HeadingAndDateTest(unittest.TestCase):
    def test_hyphen_instead_of_em_dash_rejected(self):
        body = SESSION_BODY.replace(f"2026-07-24 {EM} Do", "2026-07-24 - Do", 1)
        found = issues_for(c.SESSION_LOG, body=body)
        self.assertTrue(any("em dash" in i for i in found))

    def test_two_headings_rejected(self):
        body = SESSION_BODY + f"\n## 2026-07-24 {EM} A second heading\n"
        found = issues_for(c.SESSION_LOG, body=body)
        self.assertTrue(any("exactly one" in i for i in found))

    def test_frontmatter_date_disagreeing_with_filename_flagged(self):
        found = issues_for(c.SESSION_LOG, frontmatter=fm_with(SESSION_FM, date="2026-07-25"))
        self.assertTrue(any("disagrees with the filename date" in i for i in found))

    def test_heading_date_disagreeing_with_filename_flagged(self):
        body = SESSION_BODY.replace("2026-07-24", "2026-07-25", 1)
        found = issues_for(c.SESSION_LOG, body=body)
        self.assertTrue(any("heading date" in i for i in found))

    def test_content_before_heading_flagged(self):
        found = issues_for(c.SESSION_LOG, body="Stray line\n" + SESSION_BODY)
        self.assertTrue(any("before the `## ` heading" in i for i in found))


class FieldsTest(unittest.TestCase):
    def test_missing_field_flagged(self):
        body = SESSION_BODY.replace("Tests: 236 passing\n", "")
        found = issues_for(c.SESSION_LOG, body=body)
        self.assertTrue(any("missing required field `Tests:`" in i for i in found))

    def test_duplicate_field_flagged(self):
        body = SESSION_BODY + "Commit: def5678\n"
        found = issues_for(c.SESSION_LOG, body=body)
        self.assertTrue(any("appears 2 times" in i for i in found))

    def test_indented_field_label_flagged(self):
        # Regression: one real session-log entry had `Files touched:` indented
        # two spaces. That is the only column-0 violation in the corpus.
        body = SESSION_BODY.replace("Files touched:", "  Files touched:")
        found = issues_for(c.SESSION_LOG, body=body)
        self.assertTrue(any("indented" in i for i in found))

    def test_indented_diagnostic_block_is_accepted(self):
        # The tool-quirks template indents its command block four spaces by
        # design — "column 0" scopes to labels, never to their content.
        self.assertEqual(issues_for(c.TOOL_QUIRKS), [])

    def test_inline_diagnostic_value_is_accepted(self):
        # Regression for the real entry whose diagnostic value sits on the
        # label line: "none needed beyond noticing the placeholders".
        body = QUIRK_BODY.replace(
            "Diagnostic steps taken (re-runnable):\n    gh --version\n",
            "Diagnostic steps taken (re-runnable): none needed beyond noticing it\n",
        )
        self.assertEqual(issues_for(c.TOOL_QUIRKS, body=body), [])

    def test_extra_field_and_interleaved_prose_accepted(self):
        # Real entries carry extra `Details:` fields, bolded standalone
        # paragraphs and markdown tables. Fields need not be contiguous.
        body = SESSION_BODY.replace(
            "Files touched:",
            "Details: some extra narrative\n\n**A bolded aside.**\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nFiles touched:",
        )
        self.assertEqual(issues_for(c.SESSION_LOG, body=body), [])


class TagGrammarTest(unittest.TestCase):
    def _session_bullet(self, tag):
        return SESSION_BODY.replace(f"[Resolved {EM} did it]", tag)

    def test_each_session_vocabulary_word_accepted(self):
        for tag in (f"[Resolved {EM} x]", "[Still accurate]", f"[New info {EM} x]"):
            with self.subTest(tag=tag):
                self.assertEqual(issues_for(c.SESSION_LOG, body=self._session_bullet(tag)), [])

    def test_qualified_variants_accepted(self):
        # All of these exist verbatim in the real log.
        for tag in (
            f"[Resolved, heuristically {EM} x]",
            f"[Resolved, with a stated residual gap {EM} x]",
            f"[Resolved for the bounded common case {EM} x]",
            f"[Resolved for 19 {EM} x]",
            f"[Still accurate, with one small, deliberately-scoped exception {EM} x]",
            f"[New info, not a clean Resolved {EM} x]",
            f"[New info, partially resolved {EM} x]",
        ):
            with self.subTest(tag=tag):
                self.assertEqual(issues_for(c.SESSION_LOG, body=self._session_bullet(tag)), [])

    def test_invented_tag_rejected(self):
        found = issues_for(c.SESSION_LOG, body=self._session_bullet(f"[Mostly fine {EM} x]"))
        self.assertTrue(any("not in the vocabulary" in i for i in found))

    def test_bullet_with_no_tag_is_not_flagged(self):
        # Regression for the real entry with four bullets and zero tags. Many
        # bullets are context, not assumptions; requiring presence would fail
        # that entry for no gain.
        body = SESSION_BODY.replace(
            f'- `claude/steering-prompts/00-shared-research-standards.md` {EM} "a quote" {EM} [Resolved {EM} did it]',
            "- Real-world context supplied directly by the repo owner, not derivable from code.",
        )
        self.assertEqual(issues_for(c.SESSION_LOG, body=body), [])

    def test_backticked_tag_is_not_treated_as_this_entrys_tag(self):
        body = SESSION_BODY.replace(
            f"[Resolved {EM} did it]", f"[Resolved {EM} uses `[Evidenced {EM} path:line]` tagging]"
        )
        self.assertEqual(issues_for(c.SESSION_LOG, body=body), [])

    def test_prose_bracket_without_em_dash_anchor_is_ignored(self):
        # Real case: `[dotted.key.path, ...]` mid-sentence is not a tag.
        body = SESSION_BODY.replace(
            "Tests: 236 passing", "Tests: a {file: [dotted.key.path, ...]} map, 236 passing"
        )
        self.assertEqual(issues_for(c.SESSION_LOG, body=body), [])

    def test_quoted_foreign_tag_alongside_own_tag_is_not_flagged(self):
        # Real case: an entry quoting tool-quirks' `[Unresolved — needs
        # research]` inside its own `[New info — ...]` bullet.
        body = SESSION_BODY.replace(
            f"[Resolved {EM} did it]",
            f"[New info {EM} the entry is tagged `[Unresolved {EM} needs research]` upstream]",
        )
        self.assertEqual(issues_for(c.SESSION_LOG, body=body), [])

    def test_partially_diagnosed_accepted_in_tool_quirks(self):
        body = QUIRK_BODY.replace(
            f"[Unresolved {EM} needs research]", f"[Partially diagnosed {EM} narrowed, not fixed]"
        )
        self.assertEqual(issues_for(c.TOOL_QUIRKS, body=body), [])

    def test_partially_diagnosed_rejected_in_session_log(self):
        found = issues_for(
            c.SESSION_LOG, body=self._session_bullet(f"[Partially diagnosed {EM} x]")
        )
        self.assertTrue(any("not in the vocabulary" in i for i in found))

    def test_invented_status_rejected_in_tool_quirks(self):
        body = QUIRK_BODY.replace(f"[Unresolved {EM} needs research]", "[Fixed]")
        found = issues_for(c.TOOL_QUIRKS, body=body)
        self.assertTrue(any("not in the vocabulary" in i for i in found))


class AnchorCoverageTest(unittest.TestCase):
    """The highest-value tests in this file.

    A tag regex that matches nothing reports "0 violations" — indistinguishable
    from a clean corpus. The session-log anchor (em-dash-space-bracket) matches
    ZERO lines in tool-quirks, where every tag follows `Status: `. Shipping one
    shared anchor would have left the tool-quirks vocabulary completely
    unenforced, in the one directory where drift has actually happened.
    """

    def test_session_anchor_finds_nothing_in_a_tool_quirks_entry(self):
        entry = write_entry(c.TOOL_QUIRKS)
        found, _ = c.count_tags(entry, c.SCHEMAS[c.SESSION_LOG])
        self.assertEqual(found, 0, "session-log's anchor must not be reused for tool-quirks")

    def test_tool_quirks_anchor_finds_the_status_tag(self):
        entry = write_entry(c.TOOL_QUIRKS)
        found, _ = c.count_tags(entry, c.SCHEMAS[c.TOOL_QUIRKS])
        self.assertEqual(found, 1)

    def test_tool_quirks_anchor_finds_nothing_in_a_session_log_entry(self):
        entry = write_entry(c.SESSION_LOG)
        found, _ = c.count_tags(entry, c.SCHEMAS[c.TOOL_QUIRKS])
        self.assertEqual(found, 0)

    def test_session_anchor_finds_the_assumption_tag(self):
        entry = write_entry(c.SESSION_LOG)
        found, _ = c.count_tags(entry, c.SCHEMAS[c.SESSION_LOG])
        self.assertEqual(found, 1)


class CommitTest(unittest.TestCase):
    def test_uncommitted_needs_no_sha(self):
        body = SESSION_BODY.replace(
            "Commit: abc1234", "Commit: uncommitted (documents an incident, not a code change)"
        )
        issues, _ = c.check_entry(write_entry(c.SESSION_LOG, body=body), known_shas=set())
        self.assertEqual(issues, [])

    def test_missing_sha_and_not_uncommitted_flagged(self):
        body = SESSION_BODY.replace("Commit: abc1234", "Commit: see the branch")
        issues, _ = c.check_entry(write_entry(c.SESSION_LOG, body=body), known_shas=set())
        self.assertTrue(any("neither a SHA nor `uncommitted`" in i for i in issues))

    def test_multi_sha_value_extracts_both(self):
        body = SESSION_BODY.replace(
            "Commit: abc1234", "Commit: e614e7c (also f969521 on the same branch)"
        )
        entry = write_entry(c.SESSION_LOG, body=body)
        _, shas = c.commit_shas(entry)
        self.assertEqual(shas, ["e614e7c", "f969521"])

    def test_first_unresolvable_sha_is_an_issue(self):
        issues, _ = c.check_entry(write_entry(c.SESSION_LOG), known_shas=set())
        self.assertTrue(any("does not resolve" in i for i in issues))

    def test_later_unresolvable_sha_is_only_a_warning(self):
        # The second SHA is free prose — it may reference another entry's
        # commit, or not be a commit at all.
        body = SESSION_BODY.replace(
            "Commit: abc1234", "Commit: abc1234 (entry added in def5678)"
        )
        issues, warnings = c.check_entry(
            write_entry(c.SESSION_LOG, body=body), known_shas={"abc1234"}
        )
        self.assertEqual(issues, [])
        self.assertTrue(any("def5678" in w for w in warnings))

    def test_hex_prose_word_does_not_fail_the_build(self):
        # "facade" is valid hex. Failing over it would be a false positive
        # nobody could act on.
        body = SESSION_BODY.replace(
            "Commit: abc1234", "Commit: abc1234 (hid the facade behind a flag)"
        )
        issues, _ = c.check_entry(write_entry(c.SESSION_LOG, body=body), known_shas={"abc1234"})
        self.assertEqual(issues, [])

    def test_no_git_mode_skips_resolution(self):
        issues, _ = c.check_entry(write_entry(c.SESSION_LOG), known_shas=None)
        self.assertEqual(issues, [])


class CrossContaminationTest(unittest.TestCase):
    def test_quirks_fields_in_a_session_log_entry_flagged(self):
        body = SESSION_BODY + "Symptom: it broke\n"
        found = issues_for(c.SESSION_LOG, body=body)
        self.assertTrue(any("wrong directory" in i for i in found))

    def test_session_log_fields_in_a_quirks_entry_flagged(self):
        body = QUIRK_BODY + "Commit: abc1234\n"
        found = issues_for(c.TOOL_QUIRKS, body=body)
        self.assertTrue(any("wrong directory" in i for i in found))


class BodyShapeTest(unittest.TestCase):
    def test_bare_separator_in_body_flagged(self):
        # Means the splitter left a separator behind, or fused two entries.
        body = SESSION_BODY + "\n---\n"
        found = issues_for(c.SESSION_LOG, body=body)
        self.assertTrue(any("bare `---`" in i for i in found))

    def test_markdown_table_rule_is_not_a_bare_separator(self):
        body = SESSION_BODY.replace(
            "Files touched:", "| a | b |\n|---|---|\n| 1 | 2 |\n\nFiles touched:"
        )
        self.assertEqual(issues_for(c.SESSION_LOG, body=body), [])

    def test_missing_trailing_newline_flagged(self):
        found = issues_for(c.SESSION_LOG, text=build(SESSION_FM, SESSION_BODY).rstrip("\n"))
        self.assertTrue(any("end with a newline" in i for i in found))

    def test_extra_trailing_newline_flagged(self):
        found = issues_for(c.SESSION_LOG, text=build(SESSION_FM, SESSION_BODY) + "\n")
        self.assertTrue(any("more than one trailing newline" in i for i in found))


class CheckDirTest(unittest.TestCase):
    def _dir_with(self, kind, names):
        d = pathlib.Path(tempfile.mkdtemp())
        fm = SESSION_FM if kind == c.SESSION_LOG else QUIRK_FM
        body = SESSION_BODY if kind == c.SESSION_LOG else QUIRK_BODY
        for name in names:
            (d / name).write_text(build(fm, body), encoding="utf-8")
        return d

    def test_clean_directory_has_no_issues(self):
        d = self._dir_with(c.SESSION_LOG, ["2026-07-24-do-a-thing.md"])
        issues, _ = c.check_dir(d, c.SESSION_LOG, known_shas={"abc1234"})
        self.assertEqual(issues, [])

    def test_issues_are_prefixed_with_the_filename(self):
        d = self._dir_with(c.SESSION_LOG, ["2026-07-24-do-a-thing.md"])
        issues, _ = c.check_dir(d, c.SESSION_LOG, known_shas=set())
        self.assertTrue(all(i.startswith("2026-07-24-do-a-thing.md: ") for i in issues))

    def test_case_only_collision_flagged(self):
        # Invisible on Windows, where this repo is developed; fatal on the
        # ubuntu-latest runner it is tested on.
        d = self._dir_with(c.SESSION_LOG, ["2026-07-24-do-a-thing.md"])
        issues = c.check_dir(d, c.SESSION_LOG, known_shas={"abc1234"})[0]
        self.assertEqual(issues, [])
        entries = [
            c.parse_entry(d / "2026-07-24-do-a-thing.md", c.SESSION_LOG),
            c.parse_entry(d / "2026-07-24-do-a-thing.md", c.SESSION_LOG),
        ]
        # Simulate the two-name case directly, since a case-insensitive
        # filesystem cannot hold both files at once.
        seen = {}
        collisions = []
        for name in ("2026-07-24-do-a-thing.md", "2026-07-24-Do-A-Thing.md"):
            if name.lower() in seen:
                collisions.append(name)
            seen[name.lower()] = name
        self.assertEqual(len(collisions), 1)
        self.assertEqual(len(entries), 2)


class GroupByTest(unittest.TestCase):
    def _entries(self, values, field="epic"):
        out = []
        for i, value in enumerate(values):
            fm = fm_with(SESSION_FM, **{field: value}) if value is not None else fm_with(
                SESSION_FM, **{field: None}
            )
            out.append(write_entry(c.SESSION_LOG, name=f"2026-07-2{i}-entry-{i}.md", frontmatter=fm))
        return out

    def test_groups_by_field_value(self):
        entries = self._entries(["repo-hygiene", "drift-check", "repo-hygiene"])
        buckets = c.group_entries(entries, "epic")
        self.assertEqual(len(buckets["repo-hygiene"]), 2)
        self.assertEqual(len(buckets["drift-check"]), 1)

    def test_missing_field_buckets_under_empty_key(self):
        entries = self._entries([None])
        buckets = c.group_entries(entries, "epic")
        self.assertIn("", buckets)

    def test_unset_bucket_prints_last_and_is_labelled(self):
        entries = self._entries([None, "repo-hygiene"])
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            c.print_groups(c.group_entries(entries, "epic"), "epic")
        output = buffer.getvalue()
        self.assertIn("(unset)", output)
        self.assertGreater(output.index("(unset)"), output.index("repo-hygiene"))

    def test_entries_sort_by_date_then_filename_within_a_bucket(self):
        entries = self._entries(["repo-hygiene", "repo-hygiene"])
        buckets = c.group_entries(entries, "epic")
        names = [e.path.name for e in buckets["repo-hygiene"]]
        self.assertEqual(names, sorted(names))


class ExitCodeTest(unittest.TestCase):
    def test_clean_is_zero(self):
        self.assertEqual(c.exit_code([]), 0)

    def test_issues_fail(self):
        self.assertEqual(c.exit_code(["something"]), 1)

    def test_there_is_no_enforce_toggle(self):
        # Guards against someone reintroducing check_llms_coverage.py's
        # ENFORCE = False here — this checker is local and deterministic and
        # has none of the reasons that flag exists for.
        self.assertFalse(hasattr(c, "ENFORCE"))


class RealCorpusTest(unittest.TestCase):
    """Runs against the actual directories. Skips until the split lands, so
    this file can be committed before the migration."""

    def _check(self, kind):
        directory = c.DEFAULT_DIRS[kind]
        if not directory.is_dir():
            self.skipTest(f"{directory} does not exist yet")
        return directory, c.load_entries(directory, kind)

    def test_session_log_directory_is_clean(self):
        directory, entries = self._check(c.SESSION_LOG)
        shas = c.collect_shas(entries)
        known = None if c.is_shallow() else c.resolve_shas(shas)
        issues, _ = c.check_dir(directory, c.SESSION_LOG, known)
        self.assertEqual(issues, [], "\n".join(issues))

    def test_tool_quirks_directory_is_clean(self):
        directory, _ = self._check(c.TOOL_QUIRKS)
        issues, _ = c.check_dir(directory, c.TOOL_QUIRKS, None)
        self.assertEqual(issues, [], "\n".join(issues))

    def test_every_tool_quirks_entry_has_exactly_one_status_tag(self):
        # The anchor-coverage guarantee against the real corpus: if the
        # tool-quirks anchor ever stops matching, this drops to 0 and fails,
        # instead of quietly reporting a clean directory.
        _, entries = self._check(c.TOOL_QUIRKS)
        for entry in entries:
            with self.subTest(entry=entry.path.name):
                found, _ = c.count_tags(entry, c.SCHEMAS[c.TOOL_QUIRKS])
                self.assertEqual(found, 1)

    def test_session_log_corpus_has_tags(self):
        _, entries = self._check(c.SESSION_LOG)
        total = sum(c.count_tags(e, c.SCHEMAS[c.SESSION_LOG])[0] for e in entries)
        self.assertGreater(total, 0, "session-log anchor matched nothing across the corpus")


if __name__ == "__main__":
    unittest.main()
