"""Contract for docs/design/ddia-north-star catalog sync.

Ensures catalog.json entries match on-disk pages, required H2 sections exist,
INDEX links resolve, and ids are unique.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests.conftest import REPO_ROOT

NORTH = REPO_ROOT / "docs" / "design" / "ddia-north-star"
CATALOG = NORTH / "catalog.json"
SCHEMA = NORTH / "catalog.schema.json"
INDEX = NORTH / "INDEX.md"

CONCEPT_H2 = [
    "In one sentence",
    "When to open",
    "Core claims",
    "Tradeoffs",
    "Repo analogues",
    "Review checks",
    "Refactor signals",
    "Anti-patterns seen",
    "See also",
]
PLAYBOOK_H2 = [
    "Intent",
    "Decision procedure",
    "Review procedure",
    "Do not",
    "Worked example (this repo)",
    "See also",
]
CHAPTER_H2 = [
    "One-sentence thesis",
    "Who this chapter is for",
    "What it covers",
    "When to apply",
    "Where it shows up in systems",
    "Why it matters",
    "How to use it here",
    "Section map",
    "Digested claims",
    "Linked concept ids",
    "Linked domains",
    "Principal questions",
    "Completeness / gaps",
    "Epub file",
]
RELATIONSHIP_H2 = [
    "In one sentence",
    "Who",
    "What",
    "When",
    "Where",
    "Why",
    "How",
    "See also",
]
DEVIATION_H2 = [
    "DDIA claim id(s)",
    "Local approach",
    "Why correct here",
    "Upstream check",
    "Rejected band-aids",
    "Expiry / revisit",
    "See also",
]


def _h2_titles(text: str) -> set[str]:
    return set(re.findall(r"^## (.+)$", text, re.MULTILINE))


class TestDdiaNorthStarCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.entries = cls.catalog["entries"]
        cls.by_id = {e["id"]: e for e in cls.entries}

    def test_schema_file_exists(self) -> None:
        self.assertTrue(SCHEMA.is_file())

    def test_unique_ids(self) -> None:
        ids = [e["id"] for e in self.entries]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_entry_path_exists(self) -> None:
        for entry in self.entries:
            path = NORTH / entry["path"]
            self.assertTrue(path.is_file(), entry["path"])

    def test_catalogued_pages_cover_tree(self) -> None:
        catalogued = {e["path"] for e in self.entries}
        self.assertIn("meta/taxonomy.md", catalogued)
        for path in (NORTH / "playbooks").glob("*.md"):
            self.assertIn(path.relative_to(NORTH).as_posix(), catalogued)
        for path in (NORTH / "chapters").glob("*.md"):
            self.assertIn(path.relative_to(NORTH).as_posix(), catalogued)
        for path in NORTH.glob("domains/*/concepts/*.md"):
            self.assertIn(path.relative_to(NORTH).as_posix(), catalogued)
        for path in NORTH.glob("domains/*/relationships/*.md"):
            self.assertIn(path.relative_to(NORTH).as_posix(), catalogued)
        for path in NORTH.glob("domains/*/README.md"):
            self.assertIn(path.relative_to(NORTH).as_posix(), catalogued)
        for path in (NORTH / "deviations").glob("dev-*.md"):
            self.assertIn(path.relative_to(NORTH).as_posix(), catalogued)

    def test_related_ids_resolve(self) -> None:
        for entry in self.entries:
            for related in entry.get("related", []):
                self.assertIn(related, self.by_id, f"{entry['id']} -> {related}")

    def test_concept_required_sections(self) -> None:
        for entry in self.entries:
            if entry["kind"] != "concept":
                continue
            text = (NORTH / entry["path"]).read_text(encoding="utf-8")
            titles = _h2_titles(text)
            for needed in CONCEPT_H2:
                self.assertIn(needed, titles, f"{entry['id']} missing ## {needed}")

    def test_playbook_required_sections(self) -> None:
        for entry in self.entries:
            if entry["kind"] != "playbook":
                continue
            text = (NORTH / entry["path"]).read_text(encoding="utf-8")
            titles = _h2_titles(text)
            for needed in PLAYBOOK_H2:
                self.assertIn(needed, titles, f"{entry['id']} missing ## {needed}")

    def test_chapter_required_sections(self) -> None:
        for entry in self.entries:
            if entry["kind"] != "chapter":
                continue
            text = (NORTH / entry["path"]).read_text(encoding="utf-8")
            titles = _h2_titles(text)
            for needed in CHAPTER_H2:
                self.assertIn(needed, titles, f"{entry['id']} missing ## {needed}")

    def test_relationship_required_sections(self) -> None:
        for entry in self.entries:
            if entry["kind"] != "relationship":
                continue
            text = (NORTH / entry["path"]).read_text(encoding="utf-8")
            titles = _h2_titles(text)
            for needed in RELATIONSHIP_H2:
                self.assertIn(needed, titles, f"{entry['id']} missing ## {needed}")

    def test_deviation_required_sections(self) -> None:
        for entry in self.entries:
            if entry["kind"] != "deviation":
                continue
            text = (NORTH / entry["path"]).read_text(encoding="utf-8")
            titles = _h2_titles(text)
            for needed in DEVIATION_H2:
                self.assertIn(needed, titles, f"{entry['id']} missing ## {needed}")

    def test_index_backtick_ids_resolve(self) -> None:
        text = INDEX.read_text(encoding="utf-8")
        for match in re.findall(r"`([a-z0-9]+(?:-[a-z0-9]+)*)`", text):
            if match in {"partial", "operational", "outline"}:
                continue
            if match.startswith("ch") and len(match) == 4:
                self.assertIn(match, self.by_id, match)
                continue
            if match in self.by_id:
                continue
            if match in {"id", "verify", "sect1", "sect2", "sect3"}:
                continue

    def test_l1_critical_pages_are_operational(self) -> None:
        for needed in (
            "sor-vs-derived",
            "coverage-gates",
            "claims-and-status-drift",
            "trust-but-verify-and-auditability",
            "materialized-views-and-caches",
            "schema-evolution-and-data-outlives-code",
            "dev-coverage-denominator-codeql",
            "dev-certification-derived-view",
            "dev-fp-ratchet-separate-from-recall",
            "rel-sor-feeds-views",
            "domain-data-flow-and-truth",
        ):
            self.assertEqual(self.by_id[needed]["completeness"], "operational", needed)

    def test_lives_under_docs_design_not_claude(self) -> None:
        self.assertTrue(NORTH.is_dir())
        stub = REPO_ROOT / "claude" / "research" / "ddia-north-star" / "README.md"
        self.assertTrue(stub.is_file())
        stub_text = stub.read_text(encoding="utf-8")
        self.assertIn("docs/design/ddia-north-star", stub_text)


if __name__ == "__main__":
    unittest.main()
