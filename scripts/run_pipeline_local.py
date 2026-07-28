#!/usr/bin/env python3
"""
run_pipeline_local.py — run the whole document-spring-repo pipeline locally,
end to end, against one target repo, with every stage's real command line and
real output on screen and in a log file.

WHY THIS EXISTS
The pipeline is normally driven by a live Claude Code session. Stage 0's
scripts are ordinary subprocesses, but Stages 1–4 are subagent fan-outs that
cannot be dispatched from a plain Python process — that is exactly why
test_pipeline_stages.py defaults to synthetic data, and why CI runs only unit
tests. So there was nothing a person could run by hand to answer the practical
question: "what does this pipeline actually do, in what order, reading what,
writing what, and what do its gates say about the result?"

This script is that. It runs every deterministic stage for real, and stands in
for the four LLM stages with mock artifacts written in the exact documented
shapes — so the real gates and checkers downstream have real input and print
real output.

WHAT IS REAL AND WHAT IS MOCK — read this before trusting any output.

  Real (actual scripts, actual results):
    run_manifest.py            init / start-stage / end-stage / finalize / summary
    spring_signal_scan.py      Stage 0 ast-grep evidence extraction
    partition_repo.py          Stage 0 adaptive grouping
    build_cross_group_edges.py Stage 0 cross-group join
    capacity_preflight.py      pre-run scale estimate
    spring_drift_check.py      post-run drift re-verification
    check_pipeline_output.py   Stage 4 gate
    citation_coverage.py       missing / mis-anchored citation worklist
    check_no_secrets_leaked.py confidentiality re-check
    test_pipeline_stages.py    opt-in real-artifacts structural pass

  Mock (this script writes them; no model is involved):
    Stage 1  summaries_group_<id>.json, summaries.json
    Stage 2  arch_fragment_<id>.md, architecture_merged.md
    Stage 3  gap_questions.json, interview_answers.json
    Stage 4  docs/<fourteen>.md

The mock artifacts are shape-faithful and citation-faithful: every
[Evidenced — path:line] tag they emit is a real file and a real line taken
from this run's own signal scan, so the gates pass honestly rather than being
handed something that could not fail. They are deliberately NOT
content-faithful — the prose is templated from annotation matches, and no
document this script writes is documentation of anything. The point is the
wiring, the artifact inventory, and the gate output, not the text.

USAGE
    python3 scripts/run_pipeline_local.py /abs/path/to/spring-repo

    # write the fourteen docs into the target repo's own docs/ (as a real run
    # does), which also enables check_pipeline_output.py's stray-write check:
    python3 scripts/run_pipeline_local.py /abs/path/to/repo --docs-in-target-repo

    # compare drift against a real earlier scan instead of this run's own:
    python3 scripts/run_pipeline_local.py /abs/path/to/repo --prior-signals old_signals.json

    # deterministic stages only (scan through capacity preflight; no mock LLM stages):
    python3 scripts/run_pipeline_local.py /abs/path/to/repo --deterministic-only

    # reuse an existing spring_signals.json and skip signal_scan:
    python3 scripts/run_pipeline_local.py /abs/path/to/repo --deterministic-only \\
        --signals-file /path/to/spring_signals.json

Artifacts and run.log land in --out-dir (default: ./local-runs/<repo>-<stamp>/),
never in the target repo, unless --docs-in-target-repo is passed.

Exit code is 0 only if every gate passed. See the STEP RESULTS table it prints
at the end for which one didn't.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
SRC_DIR = os.path.join(REPO_ROOT, "src")
sys.path.insert(0, SCRIPT_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from _shared_excludes import DEFAULT_EXCLUDED_DIRS  # noqa: E402
from doc_tag_utils import VALID_DOC_FILES  # noqa: E402
from doc_engine.pipeline.context import PipelineContext, StageKind  # noqa: E402
from doc_engine.pipeline.executor import MockStageExecutor  # noqa: E402
from doc_engine.pipeline.runner import PipelineRunner  # noqa: E402
from doc_engine.pipeline.stages import build_stage_specs  # noqa: E402

# The em dash the tag grammar requires, spelled as an escape rather than a
# literal so a copy/paste through a lossy encoding can't silently downgrade it
# to a hyphen — which is the exact malformed-tag case doc_tag_utils.py's
# find_malformed_tags() exists to catch, and would make this script's own
# output fail the gate it is trying to demonstrate.
EM = "—"

# Stage names run_manifest.py records. Source of truth for the vocabulary:
# skills/document-spring-repo/SKILL.md's concurrency contract, which names
# exactly these six and requires one start/end pair each, from the
# orchestrating thread only.
STAGE_SIGNAL_SCAN = "signal_scan"
STAGE_PARTITION = "partition"
STAGE_FILE_SUMMARIZE = "file_summarize"
STAGE_ARCHITECT = "architect"
STAGE_GAP_INTERVIEW = "gap_analysis_interview"
STAGE_DOC_WRITER = "doc_writer"

# The fourteen output files, in the taxonomy's own order. VALID_DOC_FILES is a
# frozenset (unordered), and a fan-out of fourteen reads better in a log when
# it comes out in a stable, documented order — so the order lives here and is
# checked against the imported set at import time rather than duplicating the
# set itself.
DOC_ORDER = [
    "readme", "architecture", "integrations", "authorization", "database",
    "operations", "observability", "troubleshooting", "configuration",
    "change_impact", "glossary", "local_development", "testing",
    "known_limitations",
]
assert set(DOC_ORDER) == set(VALID_DOC_FILES), (
    "DOC_ORDER has drifted from doc_tag_utils.VALID_DOC_FILES"
)

# Which signal-scan evidence buckets feed which document. Mirrors
# spring_signal_scan.py's own docstring mapping ("Output buckets map directly
# to documentation categories") plus doc-taxonomy.md, and is used here only to
# pick plausible citations for the mock docs.
DOC_BUCKETS = {
    "readme": ["api_surface", "persistence"],
    "architecture": ["api_surface", "persistence", "messaging"],
    "integrations": ["api_surface", "outbound_clients", "messaging"],
    "authorization": ["security"],
    "database": ["persistence", "raw_queries"],
    "operations": ["deployment", "configuration"],
    "observability": ["observability"],
    "troubleshooting": ["error_handling", "observability"],
    "configuration": ["configuration"],
    "change_impact": ["references", "api_surface"],
    "glossary": ["persistence", "api_surface"],
    "local_development": ["deployment", "configuration"],
    "testing": ["testing"],
    "known_limitations": [],
}

# How an evidence bucket's match reads as a sentence. Keeps the mock prose from
# being fourteen copies of one line, and — more usefully — makes each claim
# name the concrete artifact it cites, which is what citation_coverage.py's
# missing-tag heuristic looks for.
BUCKET_PHRASING = {
    "api_surface": "`{file}` contributes to the HTTP API surface (`{match}`)",
    "outbound_clients": "`{file}` calls out to another service (`{match}`)",
    "messaging": "`{file}` participates in asynchronous messaging (`{match}`)",
    "persistence": "`{file}` maps application state to storage (`{match}`)",
    "raw_queries": "`{file}` issues a hand-written query (`{match}`)",
    "security": "`{file}` carries an access-control annotation (`{match}`)",
    "configuration": "`{file}` supplies externalized configuration (`{match}`)",
    "error_handling": "`{file}` handles or translates errors (`{match}`)",
    "observability": "`{file}` emits operational signal (`{match}`)",
    "deployment": "`{file}` is part of how this service is built or deployed (`{match}`)",
    "testing": "`{file}` is exercised by the test suite (`{match}`)",
    "references": "`{file}` depends on another file in this repo (`{match}`)",
}

SPRING_ROLE_BY_BUCKET = {
    "api_surface": "controller",
    "persistence": "repository",
    "raw_queries": "repository",
    "security": "security",
    "configuration": "config",
    "messaging": "messaging-producer",
    "testing": "test",
}


class Log:
    """Tee to stdout and run.log.

    Everything this script prints goes to both, so the log file is a complete
    transcript rather than a summary — the user asked to see the logs, and a
    log that omits what scrolled past is worse than no log.
    """

    def __init__(self, path):
        self.path = path
        self.fh = open(path, "w", encoding="utf-8")
        # Console encoding on Windows is frequently cp1252, which cannot
        # represent the em dash the tag grammar requires. Replace on the
        # console rather than crash; the log file is UTF-8 and keeps it.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")
                except (ValueError, OSError):
                    pass

    def __call__(self, msg=""):
        text = str(msg)
        print(text)
        self.fh.write(text + "\n")
        self.fh.flush()

    def rule(self, title):
        self("")
        self("=" * 78)
        self(title)
        self("=" * 78)

    def close(self):
        self.fh.close()


class Runner:
    """Runs the pipeline's steps, records each one's outcome, prints a table."""

    def __init__(self, log, keep_going):
        self.log = log
        self.keep_going = keep_going
        self.results = []  # (label, status, seconds, detail)
        self.aborted = False

    def record(self, label, status, seconds, detail=""):
        self.results.append((label, status, seconds, detail))

    def run(self, label, argv, gate=False, critical=False, cwd=None, env=None,
            quiet=False):
        """Run one subprocess, echoing its exact command line and full output.

        gate=True     a non-zero exit is a real failure of the run, not just
                      information — it lands in the table as FAIL and makes
                      this script's own exit code non-zero.
        critical=True a non-zero exit means nothing downstream can be
                      meaningful, so stop (unless --keep-going).
        quiet=True    for the manifest bookkeeping calls, whose one-line
                      output would otherwise drown the stages themselves.
        """
        if self.aborted:
            self.record(label, "SKIPPED", 0.0, "aborted earlier")
            return None

        printable = " ".join(_quote(a) for a in argv)
        if quiet:
            self.log(f"  $ {printable}")
        else:
            self.log("")
            self.log(f"--- {label}")
            self.log(f"  $ {printable}")

        started = time.time()
        try:
            proc = subprocess.run(
                argv, cwd=cwd, env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
        except FileNotFoundError as exc:
            elapsed = time.time() - started
            self.log(f"  !! could not execute: {exc}")
            self.record(label, "ERROR", elapsed, str(exc))
            if critical and not self.keep_going:
                self.aborted = True
            return None

        elapsed = time.time() - started
        body = (proc.stdout or "") + (proc.stderr or "")
        for line in body.rstrip("\n").splitlines():
            self.log(f"  | {line}")

        if proc.returncode == 0:
            status = "OK"
        elif gate:
            status = "FAIL"
        else:
            status = "NONZERO"
        self.log(f"  -> exit {proc.returncode} in {elapsed:.2f}s")
        self.record(label, status, elapsed, f"exit {proc.returncode}")

        if proc.returncode != 0 and critical and not self.keep_going:
            self.log("")
            self.log(f"  !! {label} is a prerequisite for every later stage "
                     f"— stopping. Re-run with --keep-going to push past it.")
            self.aborted = True
        return proc

    def mock(self, label, fn):
        """Run one of the four mocked LLM stages."""
        if self.aborted:
            self.record(label, "SKIPPED", 0.0, "aborted earlier")
            return None
        self.log("")
        self.log(f"--- {label}")
        started = time.time()
        try:
            detail = fn()
        except Exception as exc:  # a broken mock shouldn't look like a gate failure
            elapsed = time.time() - started
            self.log(f"  !! mock stage raised: {exc!r}")
            self.record(label, "ERROR", elapsed, repr(exc))
            if not self.keep_going:
                self.aborted = True
            return None
        elapsed = time.time() - started
        self.record(label, "MOCK", elapsed, detail or "")
        self.log(f"  -> {detail}")
        self.log(f"  -> {elapsed:.2f}s")
        return detail

    def gates_failed(self):
        return [r for r in self.results if r[1] in ("FAIL", "ERROR")]

    def table(self):
        self.log.rule("STEP RESULTS")
        width = max(len(r[0]) for r in self.results)
        for label, status, seconds, detail in self.results:
            self.log(f"  {status:<8} {label:<{width}}  {seconds:6.2f}s  {detail}")


def _quote(arg):
    return f'"{arg}"' if " " in arg else arg


def _script(name):
    return os.path.join(SCRIPT_DIR, name)


# --------------------------------------------------------------------------
# Evidence handling for the mock stages
# --------------------------------------------------------------------------

def load_citations(signals, repo_path):
    """Build a bucket -> [(file, line, match)] pool of citations that actually
    resolve.

    Every candidate is checked against the file on disk the same way
    doc_tag_utils.resolve_evidenced_citations() will check it later, so the
    mock docs cannot emit a citation the gate would reject. A scan is normally
    self-consistent with the repo it just scanned; this filter matters when the
    repo changed under the run, and it's cheap.
    """
    line_counts = {}

    def resolves(relpath, line):
        if relpath not in line_counts:
            abspath = os.path.join(repo_path, relpath)
            if not os.path.isfile(abspath):
                line_counts[relpath] = 0
            else:
                try:
                    with open(abspath, encoding="utf-8", errors="replace") as f:
                        line_counts[relpath] = sum(1 for _ in f)
                except OSError:
                    line_counts[relpath] = 0
        count = line_counts[relpath]
        return count > 0 and (line is None or 1 <= line <= count)

    pool = {}
    for bucket, rows in (signals.get("evidence") or {}).items():
        kept = []
        for row in rows:
            relpath = row.get("file")
            line = row.get("line")
            if not relpath or not isinstance(line, int) or line < 1:
                continue
            if not resolves(relpath, line):
                continue
            match = (row.get("match") or "").strip().replace("\n", " ")
            match = re.sub(r"\s+", " ", match)[:60] or bucket
            # A backtick inside the match would break the inline-code span the
            # phrasing templates wrap it in.
            kept.append((relpath, line, match.replace("`", "'")))
        pool[bucket] = kept
    return pool


def pick(pool, buckets, limit):
    """Take up to `limit` citations spread across `buckets`, round-robin, so a
    doc fed by three buckets doesn't get `limit` rows of the first one."""
    lists = [list(pool.get(b) or []) for b in buckets]
    out = []
    i = 0
    while len(out) < limit and any(lists):
        # strict=True documents a real invariant rather than appeasing the
        # linter: `lists` is built by comprehension over `buckets` directly
        # above, so unequal lengths would mean that line changed and this one
        # did not.
        for bucket, rows in zip(buckets, lists, strict=True):
            if not rows:
                continue
            if i < len(rows):
                out.append((bucket, rows[i]))
                if len(out) >= limit:
                    break
        if not any(i < len(rows) for rows in lists):
            break
        i += 1
    return out


def evidenced(relpath, line):
    """A well-formed [Evidenced — path:line] tag.

    Paths go out with forward slashes: the tag is read back by
    resolve_evidenced_citations(), which os.path.join()s it onto the repo root,
    and a Windows backslash in a document is both wrong-looking and needlessly
    platform-specific.
    """
    return f"[Evidenced {EM} {relpath.replace(os.sep, '/')}:{line}]"


def unknown_tag():
    return f"[Unknown {EM} not evidenced in code, not covered in interview]"


def confirmed_tag(date):
    return f"[Confirmed {EM} interview, {date}]"


def per_existing_docs_tag(filename):
    return f"[Per existing docs {EM} {filename}, unverified against code]"


# --------------------------------------------------------------------------
# TODO/FIXME sweep (Stage 0's "grep for these yourself" step)
# --------------------------------------------------------------------------

TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
TEXTUAL_SUFFIXES = {
    ".java", ".kt", ".xml", ".yml", ".yaml", ".properties", ".sql", ".gradle",
    ".md", ".json", ".sh", ".conf", ".txt", ".dockerfile",
}


def sweep_todos(repo_path, cap=200):
    """SKILL.md Stage 0: 'grep for TODO|FIXME|XXX|HACK yourself (not worth a
    dedicated script) and keep the hits — they feed known_limitations.md as
    candidates, not facts.' Done in-process, honoring the same excluded-dir set
    the scan and partition stages share."""
    hits = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs
                   if d not in DEFAULT_EXCLUDED_DIRS and not d.startswith(".")]
        for name in files:
            suffix = os.path.splitext(name)[1].lower()
            if suffix not in TEXTUAL_SUFFIXES and name.lower() != "dockerfile":
                continue
            abspath = os.path.join(root, name)
            relpath = os.path.relpath(abspath, repo_path).replace(os.sep, "/")
            try:
                with open(abspath, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        m = TODO_RE.search(line)
                        if m:
                            hits.append({
                                "file": relpath,
                                "line": lineno,
                                "marker": m.group(1),
                                "text": line.strip()[:200],
                            })
                            if len(hits) >= cap:
                                return hits
            except OSError:
                continue
    return hits


# --------------------------------------------------------------------------
# Mock Stage 1 — file summaries
# --------------------------------------------------------------------------

def mock_file_summaries(out_dir, groups, pool, edges, log):
    """One summaries_group_<id>.json per group, in agents/file-summarizer.md's
    documented shape, then the concatenation into summaries.json that SKILL.md
    does with a one-liner.

    Shape is enforced by test_pipeline_stages.py's
    validate_file_summarizer_entries() — required keys, spring_role from the
    enumerated list, and the {"line": int, "what": str} evidence anchors. That
    suite runs against this output at the end of the run, so a drift between
    this mock and the real contract shows up as a test failure rather than
    quietly producing artifacts nothing would accept.
    """
    by_file = {}
    for bucket, rows in pool.items():
        for relpath, line, match in rows:
            by_file.setdefault(relpath, []).append((bucket, line, match))

    written = []
    for group in groups["groups"]:
        gid = group["id"]
        group_edges = (edges.get("groups") or {}).get(str(gid), {})
        cross = []
        for arc in (group_edges.get("outbound") or [])[:5]:
            cross.append(json.dumps(arc, sort_keys=True)[:200])
        for block in (group_edges.get("same_package_outside") or [])[:5]:
            cross.append(json.dumps(block, sort_keys=True)[:200])

        entries = []
        for relpath in group["files"]:
            signals_for_file = by_file.get(relpath, [])
            role = "other"
            for bucket, _line, _match in signals_for_file:
                if bucket in SPRING_ROLE_BY_BUCKET:
                    role = SPRING_ROLE_BY_BUCKET[bucket]
                    break
            siblings = [f for f in group["files"] if f != relpath][:4]
            entries.append({
                "file": relpath,
                "cluster": siblings,
                "summary": (
                    f"MOCK SUMMARY (no model produced this): {relpath} was placed in "
                    f"group {gid} and carries {len(signals_for_file)} deterministic "
                    f"signal-scan hit(s)."
                ),
                "relationships": siblings[:2],
                "cross_group_relationships": cross,
                "group_function": f"MOCK group function for group {gid}",
                "spring_role": role,
                "evidence": [
                    {"line": line, "what": f"signal-scan hit: {match}"}
                    for _bucket, line, match in signals_for_file[:4]
                ],
            })

        path = os.path.join(out_dir, f"summaries_group_{gid}.json")
        _write_json(path, entries)
        written.append(path)
        log(f"  wrote {os.path.basename(path)} ({len(entries)} file entries, "
            f"{len(cross)} cross-group arc(s) attached)")

    combined = []
    for path in written:
        with open(path, encoding="utf-8") as f:
            combined.extend(json.load(f))
    _write_json(os.path.join(out_dir, "summaries.json"), combined)
    log(f"  wrote summaries.json ({len(combined)} entries from {len(written)} group file(s))")
    return f"{len(written)} group file(s), {len(combined)} file summaries"


# --------------------------------------------------------------------------
# Mock Stage 2 — architecture fragments and merge
# --------------------------------------------------------------------------

def _node_id(relpath, seen):
    base = re.sub(r"[^A-Za-z0-9]", "_", os.path.basename(relpath))
    node = base or "n"
    suffix = 2
    while node in seen:
        node = f"{base}_{suffix}"
        suffix += 1
    seen.add(node)
    return node


def mock_architecture(out_dir, groups, pool, log):
    """arch_fragment_<id>.md per group plus one architecture_merged.md.

    Node labels are real file basenames, never paraphrased — that's
    agents/architect-segment.md rule 3, and test_pipeline_stages.py's
    find_untraceable_nodes() is the mechanical check for it.
    """
    interesting = set()
    for bucket in ("api_surface", "security", "persistence", "raw_queries",
                   "messaging", "outbound_clients"):
        for relpath, _line, _match in pool.get(bucket) or []:
            interesting.add(relpath)

    fragments = []
    for group in groups["groups"]:
        gid = group["id"]
        files = [f for f in group["files"] if f in interesting] or group["files"][:6]
        files = files[:12]
        seen = set()
        nodes = [(relpath, _node_id(relpath, seen)) for relpath in files]

        lines = [
            f"# MOCK architecture fragment {EM} group {gid}",
            "",
            "Generated by scripts/run_pipeline_local.py, not by architect-segment.",
            "Node labels are real file names; the edges are adjacency within the",
            "group, not analyzed call flow.",
            "",
            "```mermaid",
            "flowchart TD",
            f"    subgraph group_{gid}[\"group {gid}\"]",
        ]
        for relpath, node in nodes:
            lines.append(f"        {node}[\"{os.path.basename(relpath)}\"]")
        lines.append("    end")
        # strict=False: the ragged tail is the point. zip(xs, xs[1:]) is the
        # pairwise-adjacent idiom, so the operands differ in length by one by
        # construction.
        for (_a, node_a), (_b, node_b) in zip(nodes, nodes[1:], strict=False):
            lines.append(f"    {node_a} --> {node_b}")
        lines.append("```")
        lines.append("")

        path = os.path.join(out_dir, f"arch_fragment_{gid}.md")
        _write_text(path, "\n".join(lines))
        fragments.append((gid, nodes, path))
        log(f"  wrote {os.path.basename(path)} ({len(nodes)} node(s))")

    merged = [
        f"# MOCK merged architecture {EM} system level",
        "",
        "Generated by scripts/run_pipeline_local.py, standing in for",
        f"architect-merge over {len(fragments)} fragment(s).",
        "",
        "```mermaid",
        "flowchart TD",
    ]
    for gid, nodes, _path in fragments:
        merged.append(f"    subgraph group_{gid}[\"group {gid}\"]")
        for relpath, node in nodes:
            merged.append(f"        {node}[\"{os.path.basename(relpath)}\"]")
        merged.append("    end")
    # strict=False for the same pairwise-adjacent reason as above; the group
    # ids are unused here, only the node lists they carry.
    for (_gid_a, nodes_a, _pa), (_gid_b, nodes_b, _pb) in zip(fragments, fragments[1:], strict=False):
        if nodes_a and nodes_b:
            merged.append(f"    {nodes_a[-1][1]} -.-> {nodes_b[0][1]}")
    merged += [
        "```",
        "",
        "## Discrepancies",
        "",
        "None identified. This is a mock merge: no pre-existing README or",
        "architecture document was compared against the diagram above, which is",
        "the comparison architect-merge would actually perform here.",
        "",
    ]
    merged_path = os.path.join(out_dir, "architecture_merged.md")
    _write_text(merged_path, "\n".join(merged))
    log(f"  wrote architecture_merged.md ({len(fragments)} fragment(s) merged)")
    return f"{len(fragments)} fragment(s) + architecture_merged.md"


# --------------------------------------------------------------------------
# Mock Stage 3 — gap questions and interview answers
# --------------------------------------------------------------------------

# Topics per document, drawn from doc-taxonomy.md's "Interview-worthy" notes —
# the categories that are structurally invisible to static analysis.
GAP_TOPICS = [
    ("integrations", "external-consumers", "Which external systems call this service, and who owns them?"),
    ("authorization", "unsecured-intent", "Is any unsecured endpoint deliberately public, or is that a gap?"),
    ("database", "write-ownership", "Which system is the authoritative writer for these tables?"),
    ("operations", "deploy-topology", "Where does this run, and what is the deploy cadence?"),
    ("known_limitations", "known-pain", "What breaks often enough that the team works around it?"),
    ("change_impact", "blast-radius", "What downstream consumer breaks first if this contract changes?"),
]


def mock_gap_and_interview(out_dir, pool, todos, today, log):
    """gap_questions.json in agents/gap-analyzer.md's shape, then the
    interview_answers.json the orchestrating thread would record.

    validate_gap_analyzer_questions() enforces three things worth naming: the
    four required keys, blocks_file drawn from the fourteen, and contiguous
    grouping by blocks_file. `evidence` must carry a real resolvable path:line
    and must not be an elided `src/.../Thing.java` — that's the one point where
    the whole [Confirmed] lane is anchored to a real location, so the mock
    takes its citations from the same verified pool the docs use.
    """
    any_citation = None
    for bucket in ("api_surface", "security", "persistence", "configuration",
                   "deployment", "observability", "references"):
        rows = pool.get(bucket) or []
        if rows:
            any_citation = rows[0]
            break
    if any_citation is None and todos:
        any_citation = (todos[0]["file"], todos[0]["line"], "TODO marker")

    questions = []
    for blocks_file, topic, prompt in GAP_TOPICS:
        buckets = DOC_BUCKETS.get(blocks_file) or []
        rows = []
        for bucket in buckets:
            rows = pool.get(bucket) or []
            if rows:
                break
        citation = rows[0] if rows else any_citation
        if citation is None:
            continue  # nothing in this repo to anchor a question to
        relpath, line, _match = citation
        questions.append({
            "blocks_file": blocks_file,
            "topic": topic,
            "question": f"MOCK QUESTION (nobody was asked this): {prompt}",
            "evidence": f"{relpath.replace(os.sep, '/')}:{line}",
        })

    _write_json(os.path.join(out_dir, "gap_questions.json"), questions)
    log(f"  wrote gap_questions.json ({len(questions)} question(s), "
        f"grouped by blocks_file)")

    # The interview itself is the one stage that structurally cannot be mocked
    # into something true: it's the orchestrating thread talking to a person.
    # So every answer is marked as a mock, and every third is a skip — because
    # SKILL.md is explicit that "asked, unanswered" must be recorded as a skip
    # rather than a blank, and a mock run should exercise that path too.
    answers = []
    for i, q in enumerate(questions):
        skipped = (i % 3 == 2)
        answers.append({
            "id": f"{q['blocks_file']}.{q['topic']}",
            "question": q["question"],
            "status": "skipped" if skipped else "answered",
            "answer": None if skipped else (
                "MOCK ANSWER: no human was interviewed for this run; this string "
                "exists so run_manifest.py's answered/skipped counts and the "
                "[Confirmed] tag lane have something to read."
            ),
            "date": today,
        })
    _write_json(os.path.join(out_dir, "interview_answers.json"), answers)
    answered = sum(1 for a in answers if a["status"] == "answered")
    log(f"  wrote interview_answers.json ({answered} answered, "
        f"{len(answers) - answered} skipped)")
    return f"{len(questions)} gap question(s), {len(answers)} recorded answer(s)"


# --------------------------------------------------------------------------
# Mock Stage 4 — the fourteen docs
# --------------------------------------------------------------------------

DOC_INTRO = (
    "> **MOCK DOCUMENT.** Written by `scripts/run_pipeline_local.py`, not by a\n"
    "> `doc-writer` subagent. The evidence tags below are real and resolvable\n"
    "> — they cite lines this run's own signal scan actually found — but the\n"
    "> prose is templated and this file documents nothing. It exists so the\n"
    "> Stage 4 gate and the citation checks have real input.\n"
)


def mock_docs(docs_dir, pool, todos, answers, today, existing_readme, log):
    """One file per taxonomy name, each carrying only well-formed tags.

    check_pipeline_output.py gates three things here: all fourteen names
    present, no writer straying outside docs/, and every [Evidenced] citation
    resolving. The first is why this iterates DOC_ORDER rather than counting to
    fourteen — two writers handed the same path produce fourteen writes with
    one name duplicated and another missing, which a count check passes.
    """
    os.makedirs(docs_dir, exist_ok=True)
    confirmed_ids = [a["id"] for a in answers if a["status"] == "answered"]
    written = []
    tag_totals = {"evidenced": 0, "confirmed": 0, "unknown": 0, "per_existing_docs": 0}

    for name in DOC_ORDER:
        body = [f"# {name.replace('_', ' ').title()}", "", DOC_INTRO, ""]

        if name == "known_limitations":
            body.append("## TODO/FIXME candidates (candidates, not facts)")
            body.append("")
            if todos:
                for hit in todos[:15]:
                    body.append(
                        f"- `{hit['file']}` carries a `{hit['marker']}` marker "
                        f"{evidenced(hit['file'], hit['line'])}."
                    )
                    tag_totals["evidenced"] += 1
            else:
                body.append(f"- No TODO/FIXME/XXX/HACK markers were found in this repo. "
                            f"Whether that reflects a clean codebase or markers tracked "
                            f"elsewhere is {unknown_tag()}.")
                tag_totals["unknown"] += 1
        else:
            picks = pick(pool, DOC_BUCKETS.get(name) or [], 8)
            body.append("## Evidenced claims")
            body.append("")
            if picks:
                for bucket, (relpath, line, match) in picks:
                    template = BUCKET_PHRASING.get(bucket, "`{file}` matched `{match}`")
                    sentence = template.format(file=relpath, match=match)
                    body.append(f"- {sentence} {evidenced(relpath, line)}.")
                    tag_totals["evidenced"] += 1
            else:
                body.append(f"- No deterministic signal-scan evidence mapped to this "
                            f"document for this repo, so its content is "
                            f"{unknown_tag()}.")
                tag_totals["unknown"] += 1

        if name == "architecture":
            body += ["", "## Merged diagram", "",
                     "See `architecture_merged.md` in the run directory; a real run "
                     "inlines it here along with its Discrepancies section."]

        body += ["", "## Interview-dependent claims", ""]
        if confirmed_ids:
            body.append(f"- Ownership and operational context for this service were "
                        f"recorded in the interview {confirmed_tag(today)}.")
            tag_totals["confirmed"] += 1
        body.append(f"- Anything not covered above is {unknown_tag()}.")
        tag_totals["unknown"] += 1

        if existing_readme:
            body += ["", "## Pre-existing documentation", "",
                     f"- The repo's own overview was read but not verified against code "
                     f"{per_existing_docs_tag(existing_readme)}."]
            tag_totals["per_existing_docs"] += 1

        body.append("")
        path = os.path.join(docs_dir, f"{name}.md")
        _write_text(path, "\n".join(body))
        written.append(path)

    log(f"  wrote {len(written)} file(s) into {docs_dir}")
    log(f"  tag totals across all fourteen: {tag_totals}")
    return f"{len(written)} docs, tags={tag_totals}"


# --------------------------------------------------------------------------

def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)


def _write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_existing_readme(repo_path):
    for name in ("README.md", "readme.md", "README.MD"):
        if os.path.isfile(os.path.join(repo_path, name)):
            return name
    return None


def main():
    ap = argparse.ArgumentParser(
        description="Run the document-spring-repo pipeline locally, end to end, "
                    "against one target repo. Deterministic stages run for real; "
                    "the four LLM stages are mocked in their documented shapes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Every stage's command line and output is echoed and also written "
               "to <out-dir>/run.log.",
    )
    ap.add_argument("repo_path", help="absolute path to the target Spring Boot repo")
    ap.add_argument("--out-dir", default=None,
                    help="where artifacts and run.log go "
                         "(default: ./local-runs/<repo>-<timestamp>)")
    ap.add_argument("--max-tokens", type=int, default=120000,
                    help="partition_repo.py --max-tokens (default: 120000, the "
                         "value SKILL.md Stage 0 uses)")
    ap.add_argument("--docs-in-target-repo", action="store_true",
                    help="write the fourteen docs into <repo>/docs/ as a real run "
                         "does, which also enables check_pipeline_output.py's "
                         "stray-write check. Off by default: this script should not "
                         "modify your repo unless you ask it to.")
    ap.add_argument("--prior-signals", default=None,
                    help="a real earlier spring_signals.json to measure drift "
                         "against (default: this run's own scan, which should "
                         "report no drift)")
    ap.add_argument("--skip-drift", action="store_true",
                    help="skip spring_drift_check.py — it re-hashes every file, "
                         "which roughly doubles scan time on a large repo")
    ap.add_argument("--respect-gitignore", action="store_true",
                    help="pass --respect-gitignore to the scan and partition stages")
    ap.add_argument("--strict-citations", action="store_true",
                    help="pass --strict to citation_coverage.py, making its "
                         "heuristic findings a gate failure")
    ap.add_argument("--keep-going", action="store_true",
                    help="continue after a failed prerequisite stage instead of "
                         "stopping")
    ap.add_argument("--deterministic-only", action="store_true",
                    help="run init + signal_scan (unless --signals-file) through "
                         "capacity_preflight only; skip mocked LLM stages and "
                         "doc-related gates")
    ap.add_argument("--signals-file", default=None,
                    help="reuse an existing spring_signals.json; copies into "
                         "--out-dir and skips the signal_scan stage")
    args = ap.parse_args()

    repo_path = os.path.abspath(args.repo_path)
    if not os.path.isdir(repo_path):
        print(f"error: {repo_path} is not a directory", file=sys.stderr)
        return 2

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = args.out_dir or os.path.join(
        os.getcwd(), "local-runs", f"{os.path.basename(repo_path.rstrip(os.sep))}-{stamp}")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    docs_dir = (os.path.join(repo_path, "docs") if args.docs_in_target_repo
                else os.path.join(out_dir, "docs"))
    today = datetime.date.today().isoformat()

    log = Log(os.path.join(out_dir, "run.log"))
    runner = Runner(log, args.keep_going)

    py = sys.executable
    manifest = os.path.join(out_dir, "run_manifest.json")
    signals_path = os.path.join(out_dir, "spring_signals.json")
    groups_path = os.path.join(out_dir, "groups.json")
    edges_path = os.path.join(out_dir, "cross_group_edges.json")
    preflight_path = os.path.join(out_dir, "capacity_preflight_report.json")
    scan_flags = ["--respect-gitignore"] if args.respect_gitignore else []

    if args.signals_file:
        signals_src = os.path.abspath(args.signals_file)
        if not os.path.isfile(signals_src):
            print(f"error: --signals-file not found: {signals_src}", file=sys.stderr)
            return 2
        shutil.copy2(signals_src, signals_path)
        log(f"  reused signals: {signals_src} -> {signals_path}")

    log.rule("document-spring-repo — LOCAL END-TO-END RUN")
    log(f"  target repo   : {repo_path}")
    log(f"  artifacts     : {out_dir}")
    log(f"  docs output   : {docs_dir}"
        f"{'  (inside the target repo)' if args.docs_in_target_repo else '  (outside the target repo)'}")
    log(f"  python        : {py}")
    if args.signals_file:
        log(f"  signals file  : {os.path.abspath(args.signals_file)} (signal_scan skipped)")
    else:
        log(f"  ast-grep      : {shutil.which('ast-grep') or 'NOT ON PATH — the signal scan will fail'}")
    log(f"  mode          : {'deterministic-only' if args.deterministic_only else 'full (mock LLM stages)'}")
    log(f"  date          : {today}")
    log("")
    if args.deterministic_only:
        log("  Deterministic stages only — no mocked LLM stages or doc gates.")
    else:
        log("  Stages 1-4 are MOCKED — no model runs. Their artifacts are")
        log("  shape-faithful and their citations resolve, but the prose is")
        log("  templated and documents nothing. Everything else is the real script.")

    pipeline_ctx = PipelineContext(
        repo_path=Path(repo_path),
        out_dir=Path(out_dir),
        manifest_path=Path(manifest),
        docs_dir=Path(docs_dir),
        python=py,
        scripts_dir=Path(SCRIPT_DIR),
        today=today,
        respect_gitignore=args.respect_gitignore,
        max_tokens=args.max_tokens,
        existing_readme=find_existing_readme(repo_path),
        log=log,
    )

    def _ensure_pool(ctx: PipelineContext):
        if ctx.pool is None and ctx.signals:
            ctx.pool = load_citations(ctx.signals, str(ctx.repo_path))
        return ctx.pool

    def handler_file_summarize(ctx: PipelineContext):
        _ensure_pool(ctx)
        return mock_file_summaries(
            str(ctx.out_dir), ctx.groups, ctx.pool, ctx.edges, log,
        )

    def handler_architect(ctx: PipelineContext):
        _ensure_pool(ctx)
        return mock_architecture(str(ctx.out_dir), ctx.groups, ctx.pool, log)

    def handler_gap(ctx: PipelineContext):
        _ensure_pool(ctx)
        if not ctx.todos:
            hits = sweep_todos(str(ctx.repo_path))
            todo_path = ctx.out_dir / "todo_hits.json"
            _write_json(str(todo_path), hits)
            ctx.todos = hits
        return mock_gap_and_interview(
            str(ctx.out_dir), ctx.pool, ctx.todos, today, log,
        )

    def handler_doc_writer(ctx: PipelineContext):
        _ensure_pool(ctx)
        answers = _read_json(str(ctx.out_dir / "interview_answers.json"))
        readme = ctx.existing_readme or find_existing_readme(str(ctx.repo_path))
        return mock_docs(
            str(ctx.docs_dir), ctx.pool, ctx.todos, answers, today, readme, log,
        )

    mock_executor = MockStageExecutor({
        "file_summarize": handler_file_summarize,
        "architect": handler_architect,
        "gap_analysis_interview": handler_gap,
        "doc_writer": handler_doc_writer,
    })

    all_specs = build_stage_specs()
    deterministic_specs = [s for s in all_specs if s.kind == StageKind.DETERMINISTIC]
    if args.signals_file:
        deterministic_specs = [s for s in deterministic_specs if s.name != "signal_scan"]
    generative_specs = [s for s in all_specs if s.kind == StageKind.GENERATIVE]

    log.rule("STAGE 0 — deterministic (PipelineRunner, real scripts)")
    det_runner = PipelineRunner(
        generative_executor=MockStageExecutor({}),
        stages=deterministic_specs,
    )
    det_results = det_runner.run(pipeline_ctx)
    for stage_name, stage_result in det_results:
        status = "OK" if stage_result.success else "FAIL"
        runner.record(
            f"pipeline:{stage_name}",
            status,
            0.0,
            stage_result.detail or stage_result.error or "",
        )
        if not stage_result.success:
            runner.aborted = True

    if runner.aborted:
        runner.table()
        log("")
        log("Run aborted before later stages — see above.")
        log.close()
        return 1

    if pipeline_ctx.signals is None and os.path.isfile(signals_path):
        pipeline_ctx.signals = _read_json(signals_path)

    pool = load_citations(pipeline_ctx.signals, repo_path)
    pipeline_ctx.pool = pool
    resolvable = sum(len(v) for v in pool.values())
    log("")
    log(f"  evidence pool: {resolvable} resolvable citation(s) across "
        f"{sum(1 for v in pool.values() if v)} non-empty bucket(s)")
    if pipeline_ctx.groups:
        log(f"  groups: {pipeline_ctx.groups['num_groups']} covering "
            f"{pipeline_ctx.groups['total_files_considered']} file(s)")

    if args.deterministic_only:
        log.rule("GATES (deterministic artifacts)")
        runner.run("validate_artifacts.py --all (B contract gate)",
                   [py, _script("validate_artifacts.py"), "--all", out_dir], gate=True)

        log.rule("FINALIZE (real)")
        fin_argv = [
            py, _script("run_manifest.py"), "finalize", manifest,
            "--signals-file", signals_path,
            "--preflight-file", preflight_path,
        ]
        runner.run("run_manifest.py finalize", fin_argv)
        runner.run("run_manifest.py summary",
                   [py, _script("run_manifest.py"), "summary", manifest])

        if not args.skip_drift:
            log.rule("DRIFT CHECK (real) — pre-flight for a future re-run")
            baseline = os.path.abspath(args.prior_signals) if args.prior_signals else signals_path
            if not args.prior_signals:
                log("  note: drift is measured against this run's own scan, so 'no drift' is")
                log("        the expected result — it exercises the script, it doesn't tell")
                log("        you anything about the repo. Use --prior-signals for a real check.")
            runner.run("spring_drift_check.py",
                       [py, _script("spring_drift_check.py"), repo_path, baseline,
                        "--manifest", manifest,
                        "--out", os.path.join(out_dir, "drift_report.json")])

        log.rule("ARTIFACT INVENTORY")
        for root, dirs, files in os.walk(out_dir):
            dirs.sort()
            for name in sorted(files):
                abspath = os.path.join(root, name)
                rel = os.path.relpath(abspath, out_dir).replace(os.sep, "/")
                log(f"  {os.path.getsize(abspath):>9,} B  {rel}")

        runner.table()
        failed = runner.gates_failed()
        log("")
        if failed:
            log(f"RESULT: {len(failed)} gate(s) failed — {', '.join(r[0] for r in failed)}")
        else:
            log("RESULT: deterministic stages complete. Run generative stages via "
                "Claude Code + document-spring-repo skill for real docs.")
        log(f"Full transcript: {os.path.join(out_dir, 'run.log')}")
        log.close()
        return 1 if failed else 0

    log.rule("STAGES 1-4 — MOCKED subagent fan-out (PipelineRunner)")
    gen_runner = PipelineRunner(generative_executor=mock_executor, stages=generative_specs)
    gen_results = gen_runner.run(pipeline_ctx)
    for stage_name, stage_result in gen_results:
        status = "MOCK" if stage_result.success else "FAIL"
        runner.record(
            f"pipeline:{stage_name}",
            status,
            0.0,
            stage_result.detail or stage_result.error or "",
        )
        if not stage_result.success:
            runner.aborted = True

    if existing_readme := find_existing_readme(repo_path):
        log("")
        log(f"  note: {existing_readme} already exists in the target repo. A real run "
            f"never overwrites it — the generated overview goes to docs/readme.md.")

    # ---------------- Gates and post-run checks ----------------
    log.rule("GATES AND POST-RUN CHECKS (real)")

    runner.run("validate_artifacts.py --all (B contract gate)",
               [py, _script("validate_artifacts.py"), "--all", out_dir], gate=True)

    runner.run("pipeline_validators.py (summaries + gap_questions gate)",
               [py, _script("pipeline_validators.py"), out_dir, "--target-repo", repo_path],
               gate=True)

    gate_argv = [py, _script("check_pipeline_output.py"), docs_dir,
                 "--target-repo", repo_path]
    if not args.docs_in_target_repo:
        # The write check compares `git status --porcelain` in the target repo
        # against the expected docs/ paths. With docs written outside the repo
        # there is nothing for it to see, so it is turned off explicitly rather
        # than left to report a confusing clean result.
        gate_argv.append("--no-write-check")
        log("")
        log("  note: --no-write-check is passed because the docs were written outside")
        log("        the target repo. Re-run with --docs-in-target-repo to exercise")
        log("        the stray-write check for real.")
    runner.run("check_pipeline_output.py (Stage 4 GATE)", gate_argv, gate=True)

    cc_argv = [py, _script("citation_coverage.py"), docs_dir, "--target-repo", repo_path]
    if args.strict_citations:
        cc_argv.append("--strict")
    runner.run("citation_coverage.py", cc_argv, gate=args.strict_citations)

    runner.run("check_no_secrets_leaked.py",
               [py, _script("check_no_secrets_leaked.py"),
                os.path.join(out_dir, "summaries.json"), docs_dir], gate=True)

    # The real structural suite, pointed at the mock artifacts. This is the
    # check that keeps the mocks honest: if a mock drifts from the documented
    # shape, it fails here instead of quietly producing artifacts no real stage
    # would accept.
    env = dict(os.environ)
    env["PIPELINE_ARTIFACTS_DIR"] = out_dir
    env["PIPELINE_ARTIFACTS_TARGET_REPO"] = repo_path
    if docs_dir != os.path.join(out_dir, "docs"):
        log("")
        log("  note: test_pipeline_stages.py's real-artifacts pass looks for docs/ inside")
        log("        PIPELINE_ARTIFACTS_DIR. With --docs-in-target-repo the docs are")
        log("        elsewhere, so its docs subtest will skip; summaries and gap")
        log("        questions are still validated.")
    runner.run("test_pipeline_stages.py -v (real suite vs. mock artifacts)",
               [py, _script("test_pipeline_stages.py"), "-v"], gate=True, env=env)

    # ---------------- Finalize ----------------
    log.rule("FINALIZE (real)")
    runner.run("run_manifest.py finalize",
               [py, _script("run_manifest.py"), "finalize", manifest,
                "--signals-file", signals_path, "--docs-dir", docs_dir,
                "--interview-file", os.path.join(out_dir, "interview_answers.json"),
                "--preflight-file", preflight_path])
    runner.run("run_manifest.py summary",
               [py, _script("run_manifest.py"), "summary", manifest])

    # ---------------- Drift check ----------------
    # Deliberately after finalize, not with the other checks above: --manifest
    # reads the manifest's `file_signatures` as the tier-1 baseline, and that
    # field is written *by* finalize. Running it earlier would hand the script a
    # manifest with nothing to compare against. This ordering also matches how
    # SKILL.md frames the tool — a pre-flight for the *next* run, measured
    # against the manifest of the run that produced the current docs.
    if not args.skip_drift:
        log.rule("DRIFT CHECK (real) — pre-flight for a future re-run")
        baseline = os.path.abspath(args.prior_signals) if args.prior_signals else signals_path
        if not args.prior_signals:
            log("  note: drift is measured against this run's own scan, so 'no drift' is")
            log("        the expected result — it exercises the script, it doesn't tell")
            log("        you anything about the repo. Use --prior-signals for a real check.")
        runner.run("spring_drift_check.py",
                   [py, _script("spring_drift_check.py"), repo_path, baseline,
                    "--manifest", manifest,
                    "--out", os.path.join(out_dir, "drift_report.json")])

    # ---------------- Inventory ----------------
    log.rule("ARTIFACT INVENTORY")
    for root, dirs, files in os.walk(out_dir):
        dirs.sort()
        for name in sorted(files):
            abspath = os.path.join(root, name)
            rel = os.path.relpath(abspath, out_dir).replace(os.sep, "/")
            log(f"  {os.path.getsize(abspath):>9,} B  {rel}")
    if args.docs_in_target_repo:
        log("")
        log(f"  plus the fourteen docs written into {docs_dir}")

    runner.table()

    failed = runner.gates_failed()
    log("")
    if failed:
        log(f"RESULT: {len(failed)} gate(s) failed — {', '.join(r[0] for r in failed)}")
    else:
        log("RESULT: every gate passed. Remember Stages 1-4 were mocked: this says the "
            "wiring and the checks work, not that any document is correct.")
    log(f"Full transcript: {os.path.join(out_dir, 'run.log')}")
    log.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
