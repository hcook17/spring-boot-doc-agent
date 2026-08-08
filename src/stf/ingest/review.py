"""Review markdown → Finding[] ingress."""

from __future__ import annotations

import re
from pathlib import Path

from stf.schemas.findings import Finding, FindingLink, FindingSeverity
from stf.schemas.spec import DataSourceRow, SpecDocument

# Simple linear heading match; id validated separately (avoids backtracking).
_HEADING = re.compile(
    r"^###\s+(?P<id>\S+)\s*[—–-]\s*(?P<title>.+)$",
    re.M,
)
_FINDING_ID = re.compile(
    r"^(?:C\d+|H\d+|M\d+|N\d+|S\d+|Q\d+-\d+|E-[A-Z0-9]+)$"
)
_SEVERITY = re.compile(r"\*\*Severity:\s*(?P<sev>[^*]+)\*\*", re.I)
_EPIC_ID = re.compile(r"^[A-Z0-9]+-\d+$")
_PATH_REF = re.compile(
    r"`((?:src|tests|adapters|scripts|docs|claude)/[^`]+)`|"
    r"```\d+:\d+:([^\n`]+)"
)

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
    m = _SEVERITY.search(text)
    if not m:
        return None
    raw = m.group("sev").strip().lower()
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


def _paths_in(text: str) -> list[str]:
    out: list[str] = []
    for m in _PATH_REF.finditer(text):
        p = m.group(1) or m.group(2)
        if p:
            out.append(p.strip())
    return list(dict.fromkeys(out))


def _links_for(fid: str, paths: list[str]) -> list[FindingLink]:
    links: list[FindingLink] = []
    for p in paths:
        links.append(FindingLink(kind="path", target=p))
        # TraceDev-style: related test / mutant heuristics
        if p.startswith("src/"):
            stem = Path(p).stem
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


def _first_claim_line(body: str) -> str:
    for line in body.splitlines()[1:8]:
        line = line.strip()
        if line and not line.startswith(("#", "|", "```")):
            return line.lstrip("*").strip()
    return ""


def _finding_from_heading_match(
    m: re.Match[str],
    body: str,
    source_doc: str | None,
) -> Finding | None:
    fid = m.group("id")
    if not _FINDING_ID.fullmatch(fid):
        return None
    title = m.group("title").strip()
    paths = _paths_in(body)
    claim = _first_claim_line(body)
    return Finding(
        id=fid,
        severity=_sev_from_id(fid, body),
        title=title,
        claim=claim or title,
        evidence=[body[:500]],
        evidence_paths=paths,
        links=_links_for(fid, paths),
        source_doc=source_doc,
        epic_hint=_epic_hint(fid),
    )


def _parse_epic_row(line: str) -> tuple[str, str, str] | None:
    """Split a markdown table row into id/title/ac without a backtracking regex."""
    if not line.startswith("|"):
        return None
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) < 4:
        return None
    tid, title, _est, ac = cells[0], cells[1], cells[2], cells[3]
    if not _EPIC_ID.fullmatch(tid):
        return None
    return tid, title, ac


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
        if not re.match(r"^[A-Z]+\d*-\d+$", tid):
            continue
        title = title or tid
        ac = ac or title
        findings.append(
            Finding(
                id=tid,
                severity=FindingSeverity.INFO,
                title=title,
                claim=ac,
                source_doc=source_doc,
                epic_hint=tid.split("-")[0],
                suggested_fix=ac,
            )
        )
        existing_ids.add(tid)
    return findings


def ingest_review_markdown(text: str, *, source_doc: str | None = None) -> list[Finding]:
    """Parse adversarial review headings into Finding inventory."""
    findings: list[Finding] = []
    matches = list(_HEADING.finditer(text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        finding = _finding_from_heading_match(m, body, source_doc)
        if finding is not None:
            findings.append(finding)

    existing = {f.id for f in findings}
    findings.extend(_findings_from_epic_rows(text, source_doc, existing))
    return findings


def _epic_hint(fid: str) -> str:
    if fid.startswith("C") or (fid.startswith("H") and fid in ("H1", "H2")):
        return "E-Q0"
    if fid.startswith(("H", "N", "M")):
        return "E-Q1"
    if fid.startswith("S"):
        return "E-Q3"
    return "E-Q4"


def ingest_review_path(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    return ingest_review_markdown(text, source_doc=str(path).replace("\\", "/"))


def findings_to_spec_seed(
    findings: list[Finding],
    *,
    target: str,
    source_review: str | None = None,
) -> SpecDocument:
    inventory = []
    for f in findings:
        if f.severity in (
            FindingSeverity.CRITICAL,
            FindingSeverity.HIGH,
            FindingSeverity.MEDIUM,
            FindingSeverity.SPIKE,
        ) or f.id.startswith(("C", "H", "N", "M", "S")):
            if f.id.startswith(("Q", "E")):
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
