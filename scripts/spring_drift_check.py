#!/usr/bin/env python3
"""
spring_drift_check.py — two-tier drift detection for spring_signals.json.

Standalone tool: takes a repo path and a prior spring_signals.json (the
output of spring_signal_scan.py's scan(), schema_version >= 2) and reports
which evidence citations in that JSON have likely drifted from the repo's
current state. Not wired into the document-spring-repo pipeline, not
triggered by CI, no LLM calls anywhere in this file — every drift verdict
here comes from a content hash or a targeted ast-grep re-run, the same
deterministic tooling spring_signal_scan.py itself is built on.

WHY TWO TIERS, NOT ONE WHOLE-FILE HASH CHECK
A single file-level content hash is a correct but coarse drift signal: if
a comment three lines away from the annotation a citation actually points
at gets fixed, the file's hash changes, and a hash-only checker would flag
every citation in that file as suspect — a false-positive drift alert on
every unrelated fact the file happens to also contain. Since ast-grep is
already this pipeline's core structural-detection dependency (see
spring_signal_scan.py / spring_ast_grep_rules.yml), the fix is to spend the
expensive, precise check only where the cheap one says something moved:

  Tier 1 (cheap, whole-repo): re-walk the repo with the exact same
  dfs_walk() spring_signal_scan.py used, hash every file with the exact
  same compute_file_signature(), and diff against the `file_signatures`
  map stored in the prior scan. This alone answers "did anything change at
  all" for every file in the repo, in one pass, with no ast-grep
  invocation.

  Tier 2 (precise, per-citation): only for files tier 1 flagged as
  changed, and only for citations that came from an ast-grep rule (i.e.
  carry a `rule_id`) — re-run run_ast_grep() against just that one file
  (confirmed empirically: ast-grep scan against a single file path returns
  the same ruleId/text/range shape as scanning a whole directory and
  filtering down to that file — no new invocation logic needed, see
  run_ast_grep() in spring_signal_scan.py) and check whether the specific
  fact the citation recorded is still present in essentially the same
  shape, not just whether the file changed somehow.

WHAT "ESSENTIALLY THE SAME SHAPE" MEANS, CONCRETELY
The stored `match` field (spring_signal_scan.py's _first_line_match — the
matched AST node's own first line, truncated to 200 chars) is *not* always
a distinctive per-citation fingerprint on its own. For a relational rule
like persistence__entity, the matched node is the whole class_declaration,
and its first line is just the leading annotation — "@Entity" for every
single entity in a repo, regardless of class name, because the class name
itself sits on the *second* line of the match (verified directly against
this plugin's own fixtures — every entity in test_fixtures/spring_signals/
has match == "@Entity", full stop). Comparing raw match text alone would
therefore either miss real drift (a different entity's match "covers" for
a citation whose actual entity disappeared) or over-report it. So this
tool re-derives, per rule type, the same specific identity
spring_signal_scan.py itself already extracts:

  persistence__entity        -> class name (_extract_entity), then verifies
                                 table/table_name_source didn't change even
                                 if the class itself is still there
  persistence__repository    -> repository interface name
                                 (_extract_repository), then verifies
                                 entity/id_type didn't change
  raw_queries__query         -> the extracted query string + query_kind
                                 (_extract_query) — not the raw annotation
                                 text, which is often multi-line
  everything else            -> the stored `match` text itself (for the
                                 remaining, mostly single-line-annotation
                                 rules, the full ast-grep match IS
                                 essentially that one line, so this is a
                                 meaningful comparison, not a fallback of
                                 convenience)

Comparison is multiset-based (collections.Counter), not 1:1 pairing: if a
file has several identically-shaped citations (possible for the generic
match-text case — e.g. two bare `@GetMapping` with no path arg, or several
plain `RestTemplate` usages), this tool can't claim to know which specific
original instance corresponds to which specific fresh match, and doesn't
pretend to; it reports however many of the original count are still
accounted for by the fresh count, and flags any shortfall as drifted.

WHAT HAPPENS TO CITATIONS WITH NO rule_id
Config/deployment/logging/migration-file evidence (spring_signal_scan.py's
pass 1, plain filename matching) has no ast-grep rule behind it at all —
there is nothing to re-run. For those, tier 2 cannot apply: if tier 1 says
the file changed, the citation is reported as
"suspected_drift_content_changed_no_rule_to_recheck" rather than silently
left unchecked or silently assumed fine. This is a deliberate, visible
fallback, not an oversight.

WHY A PLAIN CONTENT HASH, NOT A GIT BLOB SHA (a design fork, resolved here)
spring_signal_scan.py's dfs_walk() reads whatever is actually sitting on
disk — uncommitted edits and untracked files included. A git blob SHA
(`git ls-tree`/`git hash-object`) only covers files tracked at HEAD: an
untracked new file has no blob SHA to compare at all, and a file with
uncommitted edits would compare against its last-committed content, not
what dfs_walk actually scanned — silently measuring drift against the
wrong baseline for exactly the repo states this scanner is otherwise happy
to run against. Both spring_signal_scan.py's compute_file_signature() and
this tool's own tier-1 re-hash use a plain sha256 of raw file bytes for
this reason — see compute_file_signature()'s own docstring in
spring_signal_scan.py for the same rationale in more detail.

WHAT THIS DELIBERATELY DOES NOT DO
No LLM calls, anywhere. No DeepWiki-style rendered HTML output — this
writes JSON only. No GitHub Actions / CI wiring — this is a script you run
by hand, pointing it at a repo and a prior scan. All three were
deliberately scoped out of this tool; ask before adding any of them here.

Usage:
    python3 spring_signal_scan.py <repo_path> --out spring_signals.json
    # ... time passes, repo changes ...
    python3 spring_drift_check.py <repo_path> spring_signals.json --out drift_report.json
"""

import argparse
import json
import os
import sys
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import spring_signal_scan  # noqa: E402


# Every citation ends up with exactly one of these — nothing is ever
# silently dropped from the report.
STATUS_UNCHANGED = "unchanged"
STATUS_CONFIRMED = "confirmed_still_present"
STATUS_DRIFTED = "drifted"
STATUS_FILE_DELETED = "file_deleted"
STATUS_NO_RULE_FALLBACK = "suspected_drift_content_changed_no_rule_to_recheck"
STATUS_UNKNOWN_NO_SIGNATURE = "unknown_no_prior_signature"


def load_signals(path):
    with open(path) as f:
        data = json.load(f)
    version = data.get("schema_version", 1)
    if version < 2:
        print(
            f"error: '{path}' was produced by an older spring_signal_scan.py "
            f"(schema_version={version}) that doesn't record file_signatures "
            f"or rule_id on evidence entries — both required for drift "
            f"detection. Re-run spring_signal_scan.py against the repo to "
            f"regenerate it, then re-run this tool against the new file.",
            file=sys.stderr,
        )
        sys.exit(1)
    return data


def tier1_scan(repo_path):
    """Fresh sha256 per file currently in repo_path, via the exact same
    dfs_walk() (and therefore the exact same EXCLUDED_DIRS) spring_signal_scan.py
    itself used — so "what changed" is judged against the same file set the
    original scan walked, not some independently reinvented notion of it."""
    current = {}
    for full in spring_signal_scan.dfs_walk(repo_path):
        rel = os.path.relpath(full, repo_path).replace("\\", "/")
        try:
            current[rel] = spring_signal_scan.compute_file_signature(full)
        except OSError as e:
            print(f"warning: could not read '{rel}': {e}", file=sys.stderr)
    return current


def classify_files(old_signatures, current_signatures):
    unchanged, changed, deleted = [], [], []
    for rel, old_sig in old_signatures.items():
        if rel not in current_signatures:
            deleted.append(rel)
        elif current_signatures[rel] != old_sig:
            changed.append(rel)
        else:
            unchanged.append(rel)
    added = [rel for rel in current_signatures if rel not in old_signatures]
    return {
        "unchanged": sorted(unchanged),
        "changed": sorted(changed),
        "deleted": sorted(deleted),
        "added": sorted(added),
    }


def all_citations(signals):
    """Yield (source, citation) for every evidence-bearing entry in the
    signals JSON — every entry in every `evidence` bucket, plus every
    entity_table_map value, tagged with where it came from so the report
    can point back at it. entity_table_map is keyed by class name, which
    the persistence bucket's parallel entity entry can't see on its own
    (that's why spring_signal_scan.py puts `class_name` directly on the
    bucket entry too) — inject it into the citation dict here from the map
    key so both representations expose the same field uniformly."""
    for bucket_name, entries in signals.get("evidence", {}).items():
        for entry in entries:
            yield ("evidence." + bucket_name, entry)
    for class_name, entry in signals.get("entity_table_map", {}).items():
        citation = dict(entry)
        citation.setdefault("class_name", class_name)
        yield ("entity_table_map." + class_name, citation)


def drift_result(source, citation, status, tier, detail=None):
    result = {
        "source": source,
        "file": citation.get("file"),
        "line": citation.get("line"),
        "rule_id": citation.get("rule_id"),
        "match": citation.get("match"),
        "status": status,
        "tier": tier,
    }
    if detail:
        result["detail"] = detail
    return result


def _recheck_entities(file_rel, fresh_matches, group):
    """group: citations whose rule_id is persistence__entity — both the
    persistence-bucket entries (existence only, no table info) and the
    entity_table_map entries (class_name injected by all_citations,
    table/table_name_source present) go through here uniformly."""
    fresh_entities = {}
    for m in fresh_matches:
        extracted = spring_signal_scan._extract_entity(file_rel, m.get("text", ""))
        if extracted:
            cname, entry = extracted
            fresh_entities[cname] = entry

    results = []
    for source, citation in group:
        cname = citation.get("class_name")
        fresh = fresh_entities.get(cname) if cname else None
        if fresh is None:
            detail = (
                f"class '{cname}' no longer matched by persistence__entity in this file"
                if cname else "citation has no class_name to re-verify against (unexpected — treating conservatively as drift)"
            )
            results.append(drift_result(source, citation, STATUS_DRIFTED, 2, detail))
        elif ("table" in citation and fresh.get("table") != citation.get("table")) or (
                "table_name_source" in citation and fresh.get("table_name_source") != citation.get("table_name_source")
        ):
            detail = f"table mapping changed: {citation.get('table')!r} -> {fresh.get('table')!r}"
            results.append(drift_result(source, citation, STATUS_DRIFTED, 2, detail))
        else:
            results.append(drift_result(source, citation, STATUS_CONFIRMED, 2))
    return results


def _recheck_repositories(fresh_matches, group):
    fresh_repos = {}
    for m in fresh_matches:
        extra = spring_signal_scan._extract_repository(m.get("text", ""))
        if extra.get("repository"):
            fresh_repos[extra["repository"]] = extra

    results = []
    for source, citation in group:
        rname = citation.get("repository")
        fresh = fresh_repos.get(rname) if rname else None
        if fresh is None:
            detail = (
                f"repository '{rname}' no longer matched by persistence__repository in this file"
                if rname else "citation has no repository name to re-verify against (unexpected — treating conservatively as drift)"
            )
            results.append(drift_result(source, citation, STATUS_DRIFTED, 2, detail))
        elif fresh.get("entity") != citation.get("entity") or fresh.get("id_type") != citation.get("id_type"):
            detail = (
                f"repository type args changed: <{citation.get('entity')}, {citation.get('id_type')}> "
                f"-> <{fresh.get('entity')}, {fresh.get('id_type')}>"
            )
            results.append(drift_result(source, citation, STATUS_DRIFTED, 2, detail))
        else:
            results.append(drift_result(source, citation, STATUS_CONFIRMED, 2))
    return results


def _recheck_queries(fresh_matches, group):
    fresh_counts = Counter()
    for m in fresh_matches:
        multi_args = m.get("metaVariables", {}).get("multi", {}).get("ARGS", [])
        qkind, qtext = spring_signal_scan._extract_query(multi_args)
        fresh_counts[(qkind, qtext)] += 1

    budget = dict(fresh_counts)
    results = []
    for source, citation in group:
        key = (citation.get("query_kind"), citation.get("query"))
        if budget.get(key, 0) > 0:
            budget[key] -= 1
            results.append(drift_result(source, citation, STATUS_CONFIRMED, 2))
        else:
            detail = "no fresh @Query match with the same query text and kind found in this file"
            results.append(drift_result(source, citation, STATUS_DRIFTED, 2, detail))
    return results


def _recheck_generic(fresh_matches, group):
    """Fallback for every rule type without a specialized extractor. Most
    of these are single-line annotation matches (api_surface, security,
    messaging, observability, ...) where the full ast-grep match text
    already equals the stored, truncated `match` field, so this is a
    meaningful shape comparison rather than a fallback of convenience."""
    fresh_counts = Counter(spring_signal_scan._first_line_match(m.get("text", "")) for m in fresh_matches)
    budget = dict(fresh_counts)
    results = []
    for source, citation in group:
        key = citation.get("match")
        if budget.get(key, 0) > 0:
            budget[key] -= 1
            results.append(drift_result(source, citation, STATUS_CONFIRMED, 2))
        else:
            detail = "no fresh match with the same text found for this rule in this file"
            results.append(drift_result(source, citation, STATUS_DRIFTED, 2, detail))
    return results


def tier2_recheck_file(repo_path, file_rel, citations_for_file, ast_grep_path):
    """citations_for_file: list of (source, citation), all sharing file_rel,
    all with a rule_id (caller filters out the no-rule_id ones first). One
    ast-grep invocation for the whole file — covering every rule_id it has
    citations for — rather than one invocation per citation or per rule."""
    full_path = os.path.join(repo_path, file_rel)
    all_matches = spring_signal_scan.run_ast_grep(ast_grep_path, full_path)

    fresh_by_rule = {}
    for m in all_matches:
        fresh_by_rule.setdefault(m["ruleId"], []).append(m)

    old_by_rule = {}
    for source, citation in citations_for_file:
        old_by_rule.setdefault(citation["rule_id"], []).append((source, citation))

    results = []
    for rule_id, group in old_by_rule.items():
        fresh = fresh_by_rule.get(rule_id, [])
        if rule_id == "persistence__entity":
            results += _recheck_entities(file_rel, fresh, group)
        elif rule_id == "persistence__repository":
            results += _recheck_repositories(fresh, group)
        elif rule_id == "raw_queries__query":
            results += _recheck_queries(fresh, group)
        else:
            results += _recheck_generic(fresh, group)
    return results


def check_drift(repo_path, signals):
    old_signatures = signals.get("file_signatures", {})
    current_signatures = tier1_scan(repo_path)
    classification = classify_files(old_signatures, current_signatures)
    changed_set = set(classification["changed"])
    deleted_set = set(classification["deleted"])
    unchanged_set = set(classification["unchanged"])

    citations_by_file = {}
    for source, citation in all_citations(signals):
        citations_by_file.setdefault(citation["file"], []).append((source, citation))

    results = []
    ast_grep_path = None  # resolved lazily — a run with nothing to tier-2-recheck needs no ast-grep at all

    for file_rel in sorted(citations_by_file):
        citations = citations_by_file[file_rel]

        if file_rel in deleted_set:
            for source, citation in citations:
                results.append(drift_result(source, citation, STATUS_FILE_DELETED, 1))
            continue

        if file_rel in unchanged_set:
            for source, citation in citations:
                results.append(drift_result(source, citation, STATUS_UNCHANGED, 1))
            continue

        if file_rel not in changed_set:
            # Cited but absent from both the prior scan's file_signatures
            # and this run's fresh hash set — e.g. a hand-edited JSON, or a
            # citation whose file signature failed to record in the first
            # place (see spring_signal_scan.py's OSError handling). Don't
            # guess either way.
            for source, citation in citations:
                results.append(drift_result(
                    source, citation, STATUS_UNKNOWN_NO_SIGNATURE, 1,
                    detail="no prior file_signatures entry for this file to compare against",
                ))
            continue

        # File content changed since the prior scan (tier 1). Split by
        # whether there's a rule to precisely recheck against.
        with_rule = [(s, c) for s, c in citations if c.get("rule_id")]
        without_rule = [(s, c) for s, c in citations if not c.get("rule_id")]

        for source, citation in without_rule:
            results.append(drift_result(
                source, citation, STATUS_NO_RULE_FALLBACK, 1,
                detail="file content changed and this citation has no rule_id to precisely recheck "
                       "(filename-based evidence, e.g. config/deployment/migration match)",
            ))

        if with_rule:
            if ast_grep_path is None:
                ast_grep_path = spring_signal_scan.find_ast_grep()
            results += tier2_recheck_file(repo_path, file_rel, with_rule, ast_grep_path)

    results.sort(key=lambda r: (r["file"] or "", r["line"] or 0, r["source"]))
    status_counts = Counter(r["status"] for r in results)

    return {
        "repo_path": os.path.abspath(repo_path),
        "prior_scan_repo_path": signals.get("repo_path"),
        "file_summary": classification,
        "citations_checked": len(results),
        "status_counts": dict(status_counts),
        "results": results,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo_path")
    ap.add_argument("signals_path", help="prior spring_signals.json to check for drift (schema_version >= 2)")
    ap.add_argument("--out", default="drift_report.json")
    args = ap.parse_args()

    if not os.path.isdir(args.repo_path):
        print(f"error: not a directory: {args.repo_path}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.signals_path):
        print(f"error: not a file: {args.signals_path}", file=sys.stderr)
        sys.exit(1)

    signals = load_signals(args.signals_path)
    report = check_drift(args.repo_path, signals)

    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)

    fs = report["file_summary"]
    print(
        f"Wrote {args.out}. Citations checked: {report['citations_checked']}. "
        f"Status counts: {report['status_counts']}. "
        f"Files: {len(fs['unchanged'])} unchanged, {len(fs['changed'])} changed, "
        f"{len(fs['deleted'])} deleted, {len(fs['added'])} added (added files carry "
        f"no prior citations, so they're informational only)."
    )


if __name__ == "__main__":
    main()