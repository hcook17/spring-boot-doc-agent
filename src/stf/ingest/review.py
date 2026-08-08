"""Review markdown → Finding[] ingress."""

from __future__ import annotations

import re
from pathlib import Path

from stf.schemas.findings import Finding, FindingLink, FindingSeverity
from stf.schemas.spec import DataSourceRow, SpecDocument

_HEADING = re.compile(
    r"^###\s+(?P<id>C\d+|H\d+|M\d+|N\d+|S\d+|Q\d+-\d+|E-[A-Z0-9]+)\s*[—–-]\s*(?P<title>.+)$",
    re.M,
)
_SEVERITY = re.compile(r"\*\*Severity:\s*(?P<sev>[^*]+)\*\*", re.I)
_EPIC_ROW = re.compile(
    r"^\|\s*(?P<id>[A-Z0-9]+-\d+)\s*\|\s*(?P<title>[^|]+)\|\s*(?P<est>[^|]*)\|\s*(?P<ac>[^|]*)\|",
    re.M,
)
_PATH_REF = re.compile(
    r"`((?:src|tests|adapters|scripts|docs|claude)/[^`]+)`|"
    r"```\d+:\d+:([^\n`]+)"
)


def _sev_from_id(fid: str, text: str) -> FindingSeverity:
    m = _SEVERITY.search(text)
    if m:
        raw = m.group("sev").strip().lower()
        if "critical" in raw:
            return FindingSeverity.CRITICAL
        if "high" in raw:
            return FindingSeverity.HIGH
        if "medium" in raw:
            return FindingSeverity.MEDIUM
        if "low" in raw:
            return FindingSeverity.LOW
        if "spike" in raw:
            return FindingSeverity.SPIKE
    if fid.startswith("C"):
        return FindingSeverity.CRITICAL
    if fid.startswith("H"):
        return FindingSeverity.HIGH
    if fid.startswith("N") or fid.startswith("M"):
        return FindingSeverity.MEDIUM
    if fid.startswith("S"):
        return FindingSeverity.SPIKE
    return FindingSeverity.INFO


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


def ingest_review_markdown(text: str, *, source_doc: str | None = None) -> list[Finding]:
    """Parse adversarial review headings into Finding inventory."""
    findings: list[Finding] = []
    matches = list(_HEADING.finditer(text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        fid = m.group("id")
        title = m.group("title").strip()
        # skip epic section tickets that look like Q0-1 inside tables — headings only
        paths = _paths_in(body)
        claim = ""
        for line in body.splitlines()[1:8]:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("|") and not line.startswith("```"):
                claim = line.lstrip("*").strip()
                break
        findings.append(
            Finding(
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
        )

    # Also pull ticket rows from epic tables
    for m in _EPIC_ROW.finditer(text):
        tid = m.group("id").strip()
        if any(f.id == tid for f in findings):
            continue
        if not re.match(r"^[A-Z]+\d*-\d+$", tid):
            continue
        title = m.group("title").strip() or tid
        ac = m.group("ac").strip() or title
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
    return findings


def _epic_hint(fid: str) -> str:
    if fid.startswith("C") or fid.startswith("H") and fid in ("H1", "H2"):
        return "E-Q0"
    if fid.startswith("H") or fid.startswith("N") or fid.startswith("M"):
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
