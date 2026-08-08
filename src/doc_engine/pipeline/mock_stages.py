"""Mock generative stages and citation helpers for local pipeline runs."""

from __future__ import annotations

import json
import os
import re

from doc_engine.core.excludes import DEFAULT_EXCLUDED_DIRS
from doc_engine.tools.doc_tag_utils import VALID_DOC_FILES

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

_FALLBACK_CITATION_BUCKETS = (
    "api_surface",
    "security",
    "persistence",
    "configuration",
    "deployment",
    "observability",
    "references",
)

_ARCHITECTURE_BUCKETS = (
    "api_surface",
    "security",
    "persistence",
    "raw_queries",
    "messaging",
    "outbound_clients",
)


def _file_line_count(repo_path, relpath, cache):
    """Return cached line count for *relpath*, or 0 when unreadable."""
    if relpath in cache:
        return cache[relpath]
    abspath = os.path.join(repo_path, relpath)
    if not os.path.isfile(abspath):
        cache[relpath] = 0
        return 0
    try:
        with open(abspath, encoding="utf-8", errors="replace") as handle:
            cache[relpath] = sum(1 for _ in handle)
    except OSError:
        cache[relpath] = 0
    return cache[relpath]


def _citation_resolves(repo_path, relpath, line, cache):
    """True when *relpath* exists and *line* is in range (or line is None)."""
    count = _file_line_count(repo_path, relpath, cache)
    if count <= 0:
        return False
    if line is None:
        return True
    return 1 <= line <= count


def _normalize_match_text(raw_match, bucket):
    """Collapse whitespace and strip backticks so phrasing templates stay valid."""
    match = (raw_match or "").strip().replace("\n", " ")
    match = re.sub(r"\s+", " ", match)[:60] or bucket
    return match.replace("`", "'")


def _try_keep_citation_row(row, repo_path, bucket, line_counts):
    """Return (relpath, line, match) when the row cites a resolvable location."""
    relpath = row.get("file")
    line = row.get("line")
    if not relpath or not isinstance(line, int) or line < 1:
        return None
    if not _citation_resolves(repo_path, relpath, line, line_counts):
        return None
    return (relpath, line, _normalize_match_text(row.get("match"), bucket))


def _kept_citations_for_bucket(rows, repo_path, bucket, line_counts):
    """Filter one evidence bucket to resolvable citations."""
    kept = []
    for row in rows:
        citation = _try_keep_citation_row(row, repo_path, bucket, line_counts)
        if citation is not None:
            kept.append(citation)
    return kept


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
    pool = {}
    for bucket, rows in (signals.get("evidence") or {}).items():
        pool[bucket] = _kept_citations_for_bucket(
            rows, repo_path, bucket, line_counts
        )
    return pool


def _take_one_round(buckets, queues, round_index, selected, limit):
    """Append one round-robin slice; return True if anything was added."""
    added_any = False
    for bucket, queue in zip(buckets, queues, strict=True):
        if round_index >= len(queue):
            continue
        selected.append((bucket, queue[round_index]))
        added_any = True
        if len(selected) >= limit:
            return True
    return added_any


def pick(pool, buckets, limit):
    """Take up to `limit` citations spread across `buckets`, round-robin, so a
    doc fed by three buckets doesn't get `limit` rows of the first one."""
    queues = [list(pool.get(bucket) or []) for bucket in buckets]
    selected = []
    round_index = 0
    while len(selected) < limit:
        added = _take_one_round(buckets, queues, round_index, selected, limit)
        if not added:
            break
        round_index += 1
    return selected


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


def _is_textual_source(name):
    """True when *name* is a source/config extension we sweep for TODO markers."""
    suffix = os.path.splitext(name)[1].lower()
    return suffix in TEXTUAL_SUFFIXES or name.lower() == "dockerfile"


def _prune_walk_dirs(dirs):
    """Mutate os.walk dirs in place to skip excluded / hidden directories."""
    dirs[:] = [
        name for name in dirs
        if name not in DEFAULT_EXCLUDED_DIRS and not name.startswith(".")
    ]


def _scan_todo_lines(handle, relpath, remaining_cap):
    """Collect TODO/FIXME hits from an open text handle, up to *remaining_cap*."""
    hits = []
    for lineno, line in enumerate(handle, 1):
        match = TODO_RE.search(line)
        if match is None:
            continue
        hits.append({
            "file": relpath,
            "line": lineno,
            "marker": match.group(1),
            "text": line.strip()[:200],
        })
        if len(hits) >= remaining_cap:
            break
    return hits


def _todo_hits_in_file(abspath, relpath, remaining_cap):
    """Read one file and return TODO hits, or [] on I/O failure."""
    try:
        with open(abspath, encoding="utf-8", errors="replace") as handle:
            return _scan_todo_lines(handle, relpath, remaining_cap)
    except OSError:
        return []


def _extend_hits_from_name(repo_path, root, name, hits, cap):
    """Append TODO hits from one walk entry when it is a textual source file."""
    if not _is_textual_source(name):
        return hits
    abspath = os.path.join(root, name)
    relpath = os.path.relpath(abspath, repo_path).replace(os.sep, "/")
    remaining = cap - len(hits)
    return hits + _todo_hits_in_file(abspath, relpath, remaining)


def _extend_hits_from_dir(repo_path, root, files, hits, cap):
    """Append TODO hits from every textual file under one walk directory."""
    for name in files:
        hits = _extend_hits_from_name(repo_path, root, name, hits, cap)
        if len(hits) >= cap:
            return hits
    return hits


def _collect_todo_hits_under(repo_path, cap):
    """Walk *repo_path* and gather up to *cap* TODO/FIXME hits."""
    hits = []
    for root, dirs, files in os.walk(repo_path):
        _prune_walk_dirs(dirs)
        hits = _extend_hits_from_dir(repo_path, root, files, hits, cap)
        if len(hits) >= cap:
            return hits
    return hits


def sweep_todos(repo_path, cap=200):
    """SKILL.md Stage 0: 'grep for TODO|FIXME|XXX|HACK yourself (not worth a
    dedicated script) and keep the hits — they feed known_limitations.md as
    candidates, not facts.' Done in-process, honoring the same excluded-dir set
    the scan and partition stages share."""
    return _collect_todo_hits_under(repo_path, cap)


# --------------------------------------------------------------------------
# Mock Stage 1 — file summaries
# --------------------------------------------------------------------------

def _index_pool_by_file(pool):
    """Invert citation pool into relpath -> [(bucket, line, match), ...]."""
    by_file = {}
    for bucket, rows in pool.items():
        for relpath, line, match in rows:
            by_file.setdefault(relpath, []).append((bucket, line, match))
    return by_file


def _cross_group_arc_snippets(group_edges):
    """Serialize a few outbound / same-package arcs for mock summary entries."""
    snippets = []
    for arc in (group_edges.get("outbound") or [])[:5]:
        snippets.append(json.dumps(arc, sort_keys=True)[:200])
    for block in (group_edges.get("same_package_outside") or [])[:5]:
        snippets.append(json.dumps(block, sort_keys=True)[:200])
    return snippets


def _spring_role_for_signals(signals_for_file):
    """Map the first recognized signal bucket to a spring_role enum value."""
    for bucket, _line, _match in signals_for_file:
        if bucket in SPRING_ROLE_BY_BUCKET:
            return SPRING_ROLE_BY_BUCKET[bucket]
    return "other"


def _summary_entry(relpath, group_id, group_files, signals_for_file, cross):
    """Build one file-summarizer entry in the contract shape."""
    siblings = [path for path in group_files if path != relpath][:4]
    return {
        "file": relpath,
        "cluster": siblings,
        "summary": (
            f"MOCK SUMMARY (no model produced this): {relpath} was placed in "
            f"group {group_id} and carries {len(signals_for_file)} deterministic "
            f"signal-scan hit(s)."
        ),
        "relationships": siblings[:2],
        "cross_group_relationships": cross,
        "group_function": f"MOCK group function for group {group_id}",
        "spring_role": _spring_role_for_signals(signals_for_file),
        "evidence": [
            {"line": line, "what": f"signal-scan hit: {match}"}
            for _bucket, line, match in signals_for_file[:4]
        ],
    }


def _write_group_summaries(out_dir, groups, by_file, edges, log):
    """Write per-group summaries_group_<id>.json files; return their paths."""
    written = []
    for group in groups["groups"]:
        group_id = group["id"]
        group_edges = (edges.get("groups") or {}).get(str(group_id), {})
        cross = _cross_group_arc_snippets(group_edges)
        entries = [
            _summary_entry(
                relpath,
                group_id,
                group["files"],
                by_file.get(relpath, []),
                cross,
            )
            for relpath in group["files"]
        ]
        path = os.path.join(out_dir, f"summaries_group_{group_id}.json")
        _write_json(path, entries)
        written.append(path)
        log(
            f"  wrote {os.path.basename(path)} ({len(entries)} file entries, "
            f"{len(cross)} cross-group arc(s) attached)"
        )
    return written


def _combine_summary_files(out_dir, written, log):
    """Concatenate group summary files into summaries.json."""
    combined = []
    for path in written:
        with open(path, encoding="utf-8") as handle:
            combined.extend(json.load(handle))
    _write_json(os.path.join(out_dir, "summaries.json"), combined)
    log(
        f"  wrote summaries.json ({len(combined)} entries from "
        f"{len(written)} group file(s))"
    )
    return combined


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
    by_file = _index_pool_by_file(pool)
    written = _write_group_summaries(out_dir, groups, by_file, edges, log)
    combined = _combine_summary_files(out_dir, written, log)
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


def _interesting_paths(pool):
    """Paths that carry architecture-relevant signal buckets."""
    interesting = set()
    for bucket in _ARCHITECTURE_BUCKETS:
        for relpath, _line, _match in pool.get(bucket) or []:
            interesting.add(relpath)
    return interesting


def _group_architecture_files(group, interesting):
    """Prefer interesting files; fall back to a short prefix of the group."""
    files = [path for path in group["files"] if path in interesting]
    if not files:
        files = group["files"][:6]
    return files[:12]


def _fragment_mermaid_lines(group_id, nodes):
    """Build one Mermaid flowchart fragment for a partition group."""
    lines = [
        f"# MOCK architecture fragment {EM} group {group_id}",
        "",
        "Generated by doc_engine.pipeline.local_runner, not by architect-segment.",
        "Node labels are real file names; the edges are adjacency within the",
        "group, not analyzed call flow.",
        "",
        "```mermaid",
        "flowchart TD",
        f"    subgraph group_{group_id}[\"group {group_id}\"]",
    ]
    for relpath, node in nodes:
        lines.append(f"        {node}[\"{os.path.basename(relpath)}\"]")
    lines.append("    end")
    # strict=False: the ragged tail is the point. zip(xs, xs[1:]) is the
    # pairwise-adjacent idiom, so the operands differ in length by one by
    # construction.
    for (_path_a, node_a), (_path_b, node_b) in zip(nodes, nodes[1:], strict=False):
        lines.append(f"    {node_a} --> {node_b}")
    lines.append("```")
    lines.append("")
    return lines


def _write_architecture_fragments(out_dir, groups, interesting, log):
    """Write arch_fragment_<id>.md files; return (group_id, nodes, path) rows."""
    fragments = []
    for group in groups["groups"]:
        group_id = group["id"]
        files = _group_architecture_files(group, interesting)
        seen = set()
        nodes = [(relpath, _node_id(relpath, seen)) for relpath in files]
        path = os.path.join(out_dir, f"arch_fragment_{group_id}.md")
        _write_text(path, "\n".join(_fragment_mermaid_lines(group_id, nodes)))
        fragments.append((group_id, nodes, path))
        log(f"  wrote {os.path.basename(path)} ({len(nodes)} node(s))")
    return fragments


def _append_subgraph_nodes(merged, group_id, nodes):
    """Append one Mermaid subgraph block for a partition group."""
    merged.append(f"    subgraph group_{group_id}[\"group {group_id}\"]")
    for relpath, node in nodes:
        merged.append(f"        {node}[\"{os.path.basename(relpath)}\"]")
    merged.append("    end")


def _cross_group_link(nodes_a, nodes_b):
    """Dotted Mermaid edge between adjacent non-empty groups, or None."""
    if not nodes_a or not nodes_b:
        return None
    return f"    {nodes_a[-1][1]} -.-> {nodes_b[0][1]}"


def _append_cross_group_links(merged, fragments):
    """Link adjacent group subgraphs with dotted edges."""
    # strict=False for the pairwise-adjacent idiom; operands differ by one.
    for (_gid_a, nodes_a, _path_a), (_gid_b, nodes_b, _path_b) in zip(
        fragments, fragments[1:], strict=False
    ):
        link = _cross_group_link(nodes_a, nodes_b)
        if link is not None:
            merged.append(link)


def _merged_architecture_lines(fragments):
    """Assemble architecture_merged.md Mermaid from per-group fragments."""
    merged = [
        f"# MOCK merged architecture {EM} system level",
        "",
        "Generated by doc_engine.pipeline.local_runner, standing in for",
        f"architect-merge over {len(fragments)} fragment(s).",
        "",
        "```mermaid",
        "flowchart TD",
    ]
    for group_id, nodes, _path in fragments:
        _append_subgraph_nodes(merged, group_id, nodes)
    _append_cross_group_links(merged, fragments)
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
    return merged


def mock_architecture(out_dir, groups, pool, log):
    """arch_fragment_<id>.md per group plus one architecture_merged.md.

    Node labels are real file basenames, never paraphrased — that's
    agents/architect-segment.md rule 3, and test_pipeline_stages.py's
    find_untraceable_nodes() is the mechanical check for it.
    """
    interesting = _interesting_paths(pool)
    fragments = _write_architecture_fragments(out_dir, groups, interesting, log)
    merged_path = os.path.join(out_dir, "architecture_merged.md")
    _write_text(merged_path, "\n".join(_merged_architecture_lines(fragments)))
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


def _first_pool_citation(pool, buckets):
    """Return the first citation found across *buckets*, or None."""
    for bucket in buckets:
        rows = pool.get(bucket) or []
        if rows:
            return rows[0]
    return None


def _fallback_citation(pool, todos):
    """Any resolvable citation, else a TODO marker, else None."""
    citation = _first_pool_citation(pool, _FALLBACK_CITATION_BUCKETS)
    if citation is not None:
        return citation
    if todos:
        return (todos[0]["file"], todos[0]["line"], "TODO marker")
    return None


def _citation_for_topic(pool, blocks_file, fallback):
    """Prefer doc-bucket evidence; fall back to a repo-wide citation."""
    citation = _first_pool_citation(pool, DOC_BUCKETS.get(blocks_file) or [])
    return citation if citation is not None else fallback


def _build_gap_questions(pool, todos):
    """Build gap_questions.json rows anchored to resolvable evidence."""
    fallback = _fallback_citation(pool, todos)
    questions = []
    for blocks_file, topic, prompt in GAP_TOPICS:
        citation = _citation_for_topic(pool, blocks_file, fallback)
        if citation is None:
            continue
        relpath, line, _match = citation
        questions.append({
            "blocks_file": blocks_file,
            "topic": topic,
            "question": f"MOCK QUESTION (nobody was asked this): {prompt}",
            "evidence": f"{relpath.replace(os.sep, '/')}:{line}",
        })
    return questions


def _build_interview_answers(questions, today):
    """Record answered/skipped interview rows (every third is skipped)."""
    answers = []
    for index, question in enumerate(questions):
        skipped = (index % 3 == 2)
        answers.append({
            "id": f"{question['blocks_file']}.{question['topic']}",
            "question": question["question"],
            "status": "skipped" if skipped else "answered",
            "answer": None if skipped else (
                "MOCK ANSWER: no human was interviewed for this run; this string "
                "exists so run_manifest.py's answered/skipped counts and the "
                "[Confirmed] tag lane have something to read."
            ),
            "date": today,
        })
    return answers


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
    questions = _build_gap_questions(pool, todos)
    _write_json(os.path.join(out_dir, "gap_questions.json"), questions)
    log(
        f"  wrote gap_questions.json ({len(questions)} question(s), "
        f"grouped by blocks_file)"
    )

    # The interview itself is the one stage that structurally cannot be mocked
    # into something true: it's the orchestrating thread talking to a person.
    # So every answer is marked as a mock, and every third is a skip — because
    # SKILL.md is explicit that "asked, unanswered" must be recorded as a skip
    # rather than a blank, and a mock run should exercise that path too.
    answers = _build_interview_answers(questions, today)
    _write_json(os.path.join(out_dir, "interview_answers.json"), answers)
    answered = sum(1 for answer in answers if answer["status"] == "answered")
    log(
        f"  wrote interview_answers.json ({answered} answered, "
        f"{len(answers) - answered} skipped)"
    )
    return f"{len(questions)} gap question(s), {len(answers)} recorded answer(s)"


# --------------------------------------------------------------------------
# Mock Stage 4 — the fourteen docs
# --------------------------------------------------------------------------

DOC_INTRO = (
    "> **MOCK DOCUMENT.** Written by `python -m doc_engine.pipeline.local_runner`, not by a\n"
    "> `doc-writer` subagent. The evidence tags below are real and resolvable\n"
    "> — they cite lines this run's own signal scan actually found — but the\n"
    "> prose is templated and this file documents nothing. It exists so the\n"
    "> Stage 4 gate and the citation checks have real input.\n"
)


def _append_known_limitations(body, todos, tag_totals):
    """Append TODO/FIXME candidate bullets for known_limitations.md."""
    body.append("## TODO/FIXME candidates (candidates, not facts)")
    body.append("")
    if not todos:
        body.append(
            f"- No TODO/FIXME/XXX/HACK markers were found in this repo. "
            f"Whether that reflects a clean codebase or markers tracked "
            f"elsewhere is {unknown_tag()}."
        )
        tag_totals["unknown"] += 1
        return
    for hit in todos[:15]:
        body.append(
            f"- `{hit['file']}` carries a `{hit['marker']}` marker "
            f"{evidenced(hit['file'], hit['line'])}."
        )
        tag_totals["evidenced"] += 1


def _append_evidenced_claims(body, pool, doc_name, tag_totals):
    """Append evidenced claim bullets for a non-known_limitations doc."""
    picks = pick(pool, DOC_BUCKETS.get(doc_name) or [], 8)
    body.append("## Evidenced claims")
    body.append("")
    if not picks:
        body.append(
            f"- No deterministic signal-scan evidence mapped to this "
            f"document for this repo, so its content is "
            f"{unknown_tag()}."
        )
        tag_totals["unknown"] += 1
        return
    for bucket, (relpath, line, match) in picks:
        template = BUCKET_PHRASING.get(bucket, "`{file}` matched `{match}`")
        sentence = template.format(file=relpath, match=match)
        body.append(f"- {sentence} {evidenced(relpath, line)}.")
        tag_totals["evidenced"] += 1


def _append_interview_section(body, confirmed_ids, today, tag_totals):
    """Append interview-dependent claims shared by every mock doc."""
    body += ["", "## Interview-dependent claims", ""]
    if confirmed_ids:
        body.append(
            f"- Ownership and operational context for this service were "
            f"recorded in the interview {confirmed_tag(today)}."
        )
        tag_totals["confirmed"] += 1
    body.append(f"- Anything not covered above is {unknown_tag()}.")
    tag_totals["unknown"] += 1


def _append_existing_docs_section(body, existing_readme, tag_totals):
    """Optionally note a pre-existing README under Per existing docs."""
    if not existing_readme:
        return
    body += [
        "",
        "## Pre-existing documentation",
        "",
        f"- The repo's own overview was read but not verified against code "
        f"{per_existing_docs_tag(existing_readme)}.",
    ]
    tag_totals["per_existing_docs"] += 1


def _build_one_doc_body(name, pool, todos, confirmed_ids, today, existing_readme, tag_totals):
    """Assemble markdown lines for one taxonomy document."""
    body = [f"# {name.replace('_', ' ').title()}", "", DOC_INTRO, ""]
    if name == "known_limitations":
        _append_known_limitations(body, todos, tag_totals)
    else:
        _append_evidenced_claims(body, pool, name, tag_totals)
    if name == "architecture":
        body += [
            "",
            "## Merged diagram",
            "",
            "See `architecture_merged.md` in the run directory; a real run "
            "inlines it here along with its Discrepancies section.",
        ]
    _append_interview_section(body, confirmed_ids, today, tag_totals)
    _append_existing_docs_section(body, existing_readme, tag_totals)
    body.append("")
    return body


def mock_docs(docs_dir, pool, todos, answers, today, existing_readme, log):
    """One file per taxonomy name, each carrying only well-formed tags.

    check_pipeline_output.py gates three things here: all fourteen names
    present, no writer straying outside docs/, and every [Evidenced] citation
    resolving. The first is why this iterates DOC_ORDER rather than counting to
    fourteen — two writers handed the same path produce fourteen writes with
    one name duplicated and another missing, which a count check passes.
    """
    os.makedirs(docs_dir, exist_ok=True)
    confirmed_ids = [answer["id"] for answer in answers if answer["status"] == "answered"]
    written = []
    tag_totals = {"evidenced": 0, "confirmed": 0, "unknown": 0, "per_existing_docs": 0}

    for name in DOC_ORDER:
        body = _build_one_doc_body(
            name, pool, todos, confirmed_ids, today, existing_readme, tag_totals
        )
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
