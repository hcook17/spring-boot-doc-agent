"""Review markdown → Finding[] ingress."""

from __future__ import annotations

import re
from pathlib import Path

from stf.schemas.findings import Finding, FindingLink, FindingSeverity
from stf.schemas.spec import DataSourceRow, SpecDocument

# Prefer plain-string parsing for markdown headings (readable; no regex backtracking).
_HEADING_DASHES = ("—", "–", "-")
_FINDING_ID = re.compile(r"^(?:[CHMNS]\d+|Q\d+-\d+|E-[A-Z0-9]+)$")
_SEVERITY_MARK = "**severity:"
_EPIC_ID = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
_PATH_TICK = re.compile(r"`((?:src|tests|adapters|scripts|docs|claude)/[^`]+)`")
_PATH_CITE = re.compile(r"```\d+:\d+:([^\n`]+)")

_SEV_KEYWORDS: tuple[tuple[str, FindingSeverity], ...] = (
    ("critical", FindingSeverity.CRITICAL),
    ("high", FindingSeverity.HIGH),
    ("medium", FindingSeverity.MEDIUM),
    ("low", FindingSeverity.LOW),
    ("spike", FindingSeverity.SPIKE),
)

_SEV_BY_PREFIX: dict[str, FindingSeverity] = {
    "C": FindingSeverity.CRITICAL,
    "H": FindingSeverity.HIGH,
    "N": FindingSeverity.MEDIUM,
    "M": FindingSeverity.MEDIUM,
    "S": FindingSeverity.SPIKE,
}


def _sev_from_severity_line(text: str) -> FindingSeverity | None:
    """Parse ``**Severity: …**`` without a backtracking regex."""
    lower = text.lower()
    start = lower.find(_SEVERITY_MARK)
    if start < 0:
        return None
    after = text[start + len(_SEVERITY_MARK) :]
    end = after.find("**")
    if end < 0:
        return None
    return _sev_from_raw(after[:end].strip().lower())


def _sev_from_raw(raw: str) -> FindingSeverity | None:
    for needle, sev in _SEV_KEYWORDS:
        if needle in raw:
            return sev
    return None


def _sev_from_id(fid: str, text: str) -> FindingSeverity:
    from_line = _sev_from_severity_line(text)
    if from_line is not None:
        return from_line
    if not fid:
        return FindingSeverity.INFO
    return _SEV_BY_PREFIX.get(fid[0], FindingSeverity.INFO)


def _paths_from_ticks(text: str) -> list[str]:
    return [match.group(1).strip() for match in _PATH_TICK.finditer(text)]


def _paths_from_cites(text: str) -> list[str]:
    return [match.group(1).strip() for match in _PATH_CITE.finditer(text)]


def _paths_in(text: str) -> list[str]:
    return list(dict.fromkeys(_paths_from_ticks(text) + _paths_from_cites(text)))


def _links_for_path(fid: str, path: str) -> list[FindingLink]:
    links = [FindingLink(kind="path", target=path)]
    if not path.startswith("src/"):
        return links
    stem = Path(path).stem
    links.append(
        FindingLink(
            kind="test",
            target=f"tests/doc_engine/test_query_artifacts.py::{stem}",
            note="heuristic related test node",
        )
    )
    links.append(
        FindingLink(
            kind="mutant",
            target=f"scripts/ratchets/mutate.py::{fid}",
            note="named mutant slot",
        )
    )
    return links


def _links_for(fid: str, paths: list[str]) -> list[FindingLink]:
    links: list[FindingLink] = []
    for path in paths:
        links.extend(_links_for_path(fid, path))
    return links


def _is_claim_line(line: str) -> bool:
    if not line:
        return False
    return not line.startswith(("#", "|", "```"))


def _first_claim_line(body: str) -> str:
    for line in body.splitlines()[1:8]:
        stripped = line.strip()
        if _is_claim_line(stripped):
            return stripped.lstrip("*").strip()
    return ""


def _parts_for_dash(rest: str, dash: str) -> tuple[str, str] | None:
    if dash not in rest:
        return None
    finding_id, _sep, title = rest.partition(dash)
    finding_id = finding_id.strip()
    title = title.strip()
    if finding_id and title:
        return finding_id, title
    return None


def _split_heading_rest(rest: str) -> tuple[str, str] | None:
    for dash in _HEADING_DASHES:
        parts = _parts_for_dash(rest, dash)
        if parts is not None:
            return parts
    return None


def _parse_heading_line(line: str) -> tuple[str, str] | None:
    """Parse ``### ID — title`` (em dash, en dash, or hyphen)."""
    stripped = line.strip()
    if not stripped.startswith("###"):
        return None
    return _split_heading_rest(stripped[3:].strip())


def _heading_starts(lines: list[str]) -> list[tuple[int, str, str]]:
    starts: list[tuple[int, str, str]] = []
    for line_no, line in enumerate(lines):
        parsed = _parse_heading_line(line)
        if parsed is None:
            continue
        finding_id, title = parsed
        starts.append((line_no, finding_id, title))
    return starts


def _section_end(starts: list[tuple[int, str, str]], index: int, n_lines: int) -> int:
    if index + 1 < len(starts):
        return starts[index + 1][0]
    return n_lines


def _sections_from_starts(
    lines: list[str], starts: list[tuple[int, str, str]]
) -> list[tuple[str, str, str]]:
    sections: list[tuple[str, str, str]] = []
    for index, (line_no, finding_id, title) in enumerate(starts):
        end_line = _section_end(starts, index, len(lines))
        body = "\n".join(lines[line_no:end_line])
        sections.append((finding_id, title, body))
    return sections


def _heading_sections(text: str) -> list[tuple[str, str, str]]:
    """Return (finding_id, title, body) for each ``###`` finding heading."""
    lines = text.splitlines()
    return _sections_from_starts(lines, _heading_starts(lines))


def _finding_from_heading(
    finding_id: str,
    title: str,
    body: str,
    source_doc: str | None,
) -> Finding | None:
    if not _FINDING_ID.fullmatch(finding_id):
        return None
    paths = _paths_in(body)
    claim = _first_claim_line(body)
    return Finding(
        id=finding_id,
        severity=_sev_from_id(finding_id, body),
        title=title,
        claim=claim or title,
        evidence=[body[:500]],
        evidence_paths=paths,
        links=_links_for(finding_id, paths),
        source_doc=source_doc,
        epic_hint=_epic_hint(finding_id),
    )


def _parse_epic_row(line: str) -> tuple[str, str, str] | None:
    if not line.startswith("|"):
        return None
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if len(cells) < 4:
        return None
    tid, title, _est, ac = cells[0], cells[1], cells[2], cells[3]
    if not _EPIC_ID.fullmatch(tid):
        return None
    return tid, title, ac


def _epic_finding(
    tid: str, title: str, ac: str, source_doc: str | None
) -> Finding:
    title = title or tid
    ac = ac or title
    return Finding(
        id=tid,
        severity=FindingSeverity.INFO,
        title=title,
        claim=ac,
        source_doc=source_doc,
        epic_hint=tid.split("-")[0],
        suggested_fix=ac,
    )


def _findings_from_epic_rows(
    text: str,
    source_doc: str | None,
    existing_ids: set[str],
) -> list[Finding]:
    findings: list[Finding] = []
    for line in text.splitlines():
        parsed = _parse_epic_row(line)
        if parsed is None:
            continue
        tid, title, ac = parsed
        if tid in existing_ids:
            continue
        findings.append(_epic_finding(tid, title, ac, source_doc))
        existing_ids.add(tid)
    return findings


def ingest_review_markdown(text: str, *, source_doc: str | None = None) -> list[Finding]:
    """Parse adversarial review headings into Finding inventory."""
    findings: list[Finding] = []
    for finding_id, title, body in _heading_sections(text):
        finding = _finding_from_heading(finding_id, title, body, source_doc)
        if finding is not None:
            findings.append(finding)
    existing = {f.id for f in findings}
    findings.extend(_findings_from_epic_rows(text, source_doc, existing))
    return findings


def _epic_hint_q0(fid: str) -> bool:
    if fid.startswith("C"):
        return True
    return fid in ("H1", "H2")


def _epic_hint(fid: str) -> str:
    if _epic_hint_q0(fid):
        return "E-Q0"
    if fid.startswith(("H", "N", "M")):
        return "E-Q1"
    if fid.startswith("S"):
        return "E-Q3"
    return "E-Q4"


def ingest_review_path(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    return ingest_review_markdown(text, source_doc=str(path).replace("\\", "/"))


def _inventory_worthy(f: Finding) -> bool:
    if f.id.startswith(("Q", "E")):
        return False
    if f.severity in (
        FindingSeverity.CRITICAL,
        FindingSeverity.HIGH,
        FindingSeverity.MEDIUM,
        FindingSeverity.SPIKE,
    ):
        return True
    return f.id.startswith(("C", "H", "N", "M", "S"))


def findings_to_spec_seed(
    findings: list[Finding],
    *,
    target: str,
    source_review: str | None = None,
) -> SpecDocument:
    inventory = []
    for f in findings:
        if not _inventory_worthy(f):
            continue
        inventory.append(
            DataSourceRow(
                id=f"INV-{f.id}",
                data_need=f.title,
                origin=f.evidence_paths[0] if f.evidence_paths else "new — to be built",
            )
        )
    critical = [f for f in findings if f.severity == FindingSeverity.CRITICAL]
    return SpecDocument(
        target=target,
        goal=f"Remediate findings from {source_review or 'adversarial review'} "
        f"({len(findings)} items; {len(critical)} critical).",
        input_kind="review_remediation",
        requirements=[f"{f.id}: {f.title}" for f in findings if f.id.startswith(("C", "H", "N", "M"))],
        inventory=inventory,
        critical_assumptions=[f.claim for f in critical],
        finding_ids=[f.id for f in findings],
        source_review=source_review,
        out_of_scope=["Do not re-litigate verified non-findings from the review."],
        decisions=[
            {
                "decision": "Server-derived root mandatory for MCP",
                "blocks": "Q0-1",
                "resolution": "locked — C1 Critical",
            },
            {
                "decision": "Payload Option A (row_ref / honest serialized budget)",
                "blocks": "Q0-2",
                "resolution": "locked",
            },
        ],
    )
