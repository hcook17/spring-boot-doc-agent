"""Depth fitness functions for docs/design/ddia-north-star.

Operational pages must earn the label: falsifiable review checks plus
epub anchors and/or concrete [Repo] path citations. Line-count padding
and shared Fail-if boilerplate alone are not enough.
"""
from __future__ import annotations

import json
import re
import unittest
from collections import Counter
from pathlib import Path

from tests.conftest import REPO_ROOT

NORTH = REPO_ROOT / "docs" / "design" / "ddia-north-star"
CATALOG = NORTH / "catalog.json"
BASELINE = NORTH / "operational_count_baseline.json"

FAIL_IF_RE = re.compile(r"(?im)^\s*[-*]?\s*Fail if\b")
FAIL_IF_LINE_RE = re.compile(r"(?im)^\s*[-*]?\s*(Fail if .+)$")
REPO_TAG_RE = re.compile(r"\[Repo\]")
BACKTICK_PATH_RE = re.compile(r"`((?:src|scripts|docs|tests|adapters|claude)/[^`\s]+)`")
SECTION_MAP_RE = re.compile(
    r"^## Section map\n(?P<body>.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL
)
H3_RE = re.compile(r"^### (.+)$", re.MULTILINE)

# Max pages that may share a Fail-if line for it to count as page-specific.
FAIL_IF_UNIQUENESS_MAX_PAGES = 5


def _section_bodies(text: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    bodies: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        bodies[title] = body
    return bodies


def _fail_if_lines(text: str) -> list[str]:
    return [m.group(1).strip() for m in FAIL_IF_LINE_RE.finditer(text)]


class TestDdiaNorthStarDepth(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.entries = cls.catalog["entries"]
        cls.by_id = {e["id"]: e for e in cls.entries}
        counts: Counter[str] = Counter()
        for entry in cls.entries:
            if entry["completeness"] != "operational":
                continue
            if entry["kind"] in {"taxonomy"}:
                continue
            text = (NORTH / entry["path"]).read_text(encoding="utf-8")
            for line in _fail_if_lines(text):
                counts[line] += 1
        cls.fail_if_page_counts = counts

    def test_operational_pages_have_fail_if(self) -> None:
        for entry in self.entries:
            if entry["completeness"] != "operational":
                continue
            if entry["kind"] in {"taxonomy"}:
                continue
            text = (NORTH / entry["path"]).read_text(encoding="utf-8")
            self.assertTrue(
                FAIL_IF_RE.search(text),
                f"{entry['id']} is operational but has no 'Fail if' check",
            )

    def test_operational_pages_have_anchor_or_repo_citation(self) -> None:
        for entry in self.entries:
            if entry["completeness"] != "operational":
                continue
            if entry["kind"] in {"taxonomy"}:
                continue
            text = (NORTH / entry["path"]).read_text(encoding="utf-8")
            has_epub = bool(entry.get("epub_anchors"))
            has_repo_tag = bool(REPO_TAG_RE.search(text))
            paths = BACKTICK_PATH_RE.findall(text)
            has_live_path = any((REPO_ROOT / p).exists() for p in paths)
            self.assertTrue(
                has_epub or has_repo_tag or has_live_path,
                f"{entry['id']} operational without epub_anchors, [Repo], "
                f"or existing backtick path citation",
            )

    def test_operational_chapters_have_section_digests(self) -> None:
        for entry in self.entries:
            if entry["kind"] != "chapter" or entry["completeness"] != "operational":
                continue
            text = (NORTH / entry["path"]).read_text(encoding="utf-8")
            m = SECTION_MAP_RE.search(text)
            self.assertIsNotNone(m, f"{entry['id']} missing Section map")
            map_body = m.group("body")
            listing = re.split(r"^### ", map_body, maxsplit=1, flags=re.MULTILINE)[0]
            bullets = re.findall(r"^- (.+)$", listing, re.MULTILINE)
            self.assertGreaterEqual(len(bullets), 1, entry["id"])
            h3s = {t.strip() for t in H3_RE.findall(text)}
            for bullet in bullets:
                title = bullet.strip()
                self.assertIn(
                    title,
                    h3s,
                    f"{entry['id']} section map item {title!r} lacks ### digest",
                )
                after = text.split(f"### {title}", 1)[1]
                until = re.split(r"^### |^## ", after, maxsplit=1, flags=re.MULTILINE)[0]
                self.assertRegex(
                    until,
                    r"(?m)^\s*[-*]",
                    f"{entry['id']} ### {title} digest has no bullets",
                )

    def test_operational_concepts_review_checks_nonempty(self) -> None:
        for entry in self.entries:
            if entry["kind"] != "concept" or entry["completeness"] != "operational":
                continue
            text = (NORTH / entry["path"]).read_text(encoding="utf-8")
            bodies = _section_bodies(text)
            review = bodies.get("Review checks", "")
            self.assertGreaterEqual(
                len(re.findall(r"(?m)^\s*[-*]\s+\S", review)),
                2,
                f"{entry['id']} Review checks need ≥2 bullets",
            )
            self.assertTrue(
                FAIL_IF_RE.search(review) or FAIL_IF_RE.search(text),
                f"{entry['id']} needs Fail if in Review checks",
            )

    def test_operational_domain_owns_local_concept(self) -> None:
        """Hollow domains (pointer-only) must not be operational."""
        for entry in self.entries:
            if entry["kind"] != "domain" or entry["completeness"] != "operational":
                continue
            path = Path(entry["path"])
            domain_dir = NORTH / path.parent
            concepts_dir = domain_dir / "concepts"
            concepts = list(concepts_dir.glob("*.md")) if concepts_dir.is_dir() else []
            self.assertGreaterEqual(
                len(concepts),
                1,
                f"{entry['id']} is operational but owns no concepts/ under "
                f"{domain_dir.name}",
            )

    def test_operational_concept_or_chapter_has_page_specific_fail_if(self) -> None:
        """Boilerplate Fail-if shared across many pages cannot alone certify."""
        for entry in self.entries:
            if entry["completeness"] != "operational":
                continue
            if entry["kind"] not in {"concept", "chapter"}:
                continue
            text = (NORTH / entry["path"]).read_text(encoding="utf-8")
            lines = _fail_if_lines(text)
            self.assertTrue(lines, f"{entry['id']} has no Fail-if lines")
            specific = [
                line
                for line in lines
                if self.fail_if_page_counts[line] < FAIL_IF_UNIQUENESS_MAX_PAGES
            ]
            self.assertTrue(
                specific,
                f"{entry['id']} has no Fail-if appearing on fewer than "
                f"{FAIL_IF_UNIQUENESS_MAX_PAGES} pages "
                f"(counts={[self.fail_if_page_counts[l] for l in lines]})",
            )

    def test_baseline_comment_key_intact(self) -> None:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.assertIn("$comment", baseline)
        self.assertNotIn("", baseline)

    def test_operational_count_ratchet(self) -> None:
        self.assertTrue(BASELINE.is_file(), "missing operational_count_baseline.json")
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        actual = sum(1 for e in self.entries if e["completeness"] == "operational")
        floor = int(baseline["min_operational_entries"])
        self.assertGreaterEqual(
            actual,
            floor,
            f"operational count {actual} dropped below baseline {floor}; "
            f"update baseline only when intentional",
        )


if __name__ == "__main__":
    unittest.main()
