#!/usr/bin/env python3
"""
spring_drift_check.py — two-tier drift detection for spring_signals.json:
which evidence citations from a prior scan no longer match the repo.

Usage:
    python -m doc_engine.tools.spring_signal_scan <repo_path> --out spring_signals.json
    # ... time passes, repo changes ...
    python -m doc_engine.tools.spring_drift_check <repo_path> spring_signals.json --out drift_report.json

    # Or, to measure drift against the specific pipeline run that produced
    # the currently-published docs, rather than the raw scan:
    python -m doc_engine.tools.spring_drift_check <repo_path> spring_signals.json \\
        --manifest run_manifest.json --out drift_report.json

Tier 1 compares content hashes to find changed files; when anything moved,
tier 2 runs one fresh ``spring_signal_scan.scan()`` of the repo (same scanner
set as the prior signals, default ``filesystem,ast-grep``) and compares each
changed-file citation against that fresh evidence bag. No LLM calls anywhere
in this file.

WHY THIS EXISTS

Standalone tool: takes a repo path and a prior spring_signals.json (the
output of spring_signal_scan.py's scan(), schema_version >= 2) and reports
which evidence citations in that JSON have likely drifted from the repo's
current state. Not wired into the document-spring-repo pipeline, not
triggered by CI, no LLM calls anywhere in this file — every drift verdict
here comes from a content hash or a compare against a fresh Stage 0 scan,
the same deterministic tooling spring_signal_scan.py itself is built on.

WHY TWO TIERS, NOT ONE WHOLE-FILE HASH CHECK
A single file-level content hash is a correct but coarse drift signal: if
a comment three lines away from the annotation a citation actually points
at gets fixed, the file's hash changes, and a hash-only checker would flag
every citation in that file as suspect — a false-positive drift alert on
every unrelated fact the file happens to also contain. The fix is to spend
the expensive, precise check only where the cheap one says something moved:

  Tier 1 (cheap, whole-repo): re-walk the repo with the exact same
  dfs_walk() spring_signal_scan.py used, hash every file with the exact
  same compute_file_signature(), and diff against the `file_signatures`
  map stored in the prior scan. This alone answers "did anything change at
  all" for every file in the repo, in one pass, with no structural scan.

  Tier 2 (precise, per-citation): when tier 1 reports any change (or
  add/delete), run one fresh ``spring_signal_scan.scan()`` of the whole
  repo using the prior signals' ``scanners`` list (default
  ``filesystem,ast-grep``), then for each changed cited file compare the
  stored citations against the fresh evidence filtered to that file/rule —
  entity/table mapping, repository type args, query text, or annotation
  shape. This is **not** a per-file ``run_ast_grep()`` subprocess; the
  fresh bag is repo-wide and filtered down. Skip the fresh scan entirely
  when tier 1 finds nothing moved.

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
there is nothing to re-run. For most of these, tier 2 cannot apply: if
tier 1 says the file changed, the citation is reported as
"suspected_drift_content_changed_no_rule_to_recheck" rather than silently
left unchecked or silently assumed fine. This is a deliberate, visible
fallback, not an oversight.

One specific exception: files spring_signal_scan.py recorded a
config_key_sets entry for (schema_version >= 5 — application*.yml/
properties, bootstrap*.yml/properties, and YAML deployment manifests) get
a real tier-2-style recheck instead of the generic fallback above, via
_recheck_config_keys(): the file's dotted key set is re-extracted
(_config_keys.py, no YAML dependency — see that module's docstring) and
compared against the stored snapshot. Key set changed -> reported as
"config_structure_changed" (an expected, structural evolution — keys
added/removed). Key set identical but the file's content hash still
changed -> reported as "config_values_only_changed_review_needed": the
only way that happens is a *value* changed under an unchanged key, which
in a setup where these files are checked-in placeholders and real values
are injected by an external service at deploy time is the anomalous case
worth a human look, not the routine one. A repo without config_key_sets
in its prior scan (an older schema_version) just gets the original
generic fallback — this is additive, not a hard requirement.

DERIVED CITATIONS HAVE MORE THAN ONE INPUT — PROVENANCE, NOT A SPECIAL CASE
Every rule above implicitly assumes a citation's freshness is a function of
exactly one file: its own. That's true for primary evidence (a
@RestController is present because that file, and only that file, says
so), which is why the per-file loop in check_drift() can get away with
"file unchanged -> citation unchanged." It stops being true the moment a
citation's value is *derived* from more than one file. JPQL lineage
(spring_signal_scan.py schema_version >= 6) is the first such citation:
its source_tables is computed from the query text (its own file) AND the
entity->table mapping resolve_jpql_to_lineage() looked up
(entity_table_map[entity]["file"], typically a different file entirely).
A table rename in the entity's file doesn't touch the query's own file at
all, so tier 1 alone would call that citation unchanged while its lineage
silently goes stale.

The fix generalizes the existing rule rather than special-casing JPQL:
"a citation is fresh iff every file in its provenance is unchanged" was
always the real invariant — every rule above just has provenance = {own
file} implicitly. resolve_jpql_to_lineage() stamps its result with
lineage.resolved_via_entity, so a JPQL citation's provenance is knowable
as {own file, entity_table_map[entity]["file"]} without any new stored
index. _reverify_jpql_lineage_provenance() runs once after the main
per-file loop (same reason spring_signal_scan.py itself defers JPQL
resolution to its own post-loop pass: ast-grep's match order isn't
guaranteed, so the entity's file and the query's file might get tier-2
rechecked in either order) and re-derives the JPQL citation's freshness
from fresh_entity_tables — the same class_name -> table map
_recheck_entities() already builds internally to do its own comparison,
exposed rather than thrown away, so this costs zero extra ast-grep
invocations. The outcome reuses STATUS_CONFIRMED/STATUS_DRIFTED, not a new
status: an entity file changing without its table mapping actually moving
(a comment edit, a new unrelated field) still confirms the lineage,
exactly like the false-positive-avoidance case every other rule already
handles. No new machinery is needed if a second derived-citation type ever
shows up later — it only needs to name its own provenance set the same
way.

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

OPTIONAL --manifest: WHICH file_signatures BASELINE TO TRUST
spring_signals.json's own file_signatures (the raw Stage 0 scan) is still
the default tier-1 baseline and is always sufficient on its own. But a
document-spring-repo pipeline run's run_manifest.json (doc_engine.tools.run_manifest)
independently records file_signatures too — either copied from the same
spring_signals.json, or a fresh re-hash at `finalize` time if the run
wasn't handed a --signals-file. When both exist and might disagree (e.g.
several pipeline runs happened against one older spring_signals.json scan,
or the repo changed between the scan and the run that actually produced
the currently-published docs), pass --manifest run_manifest.json to use
its file_signatures as the tier-1 baseline instead of spring_signals.json's.
spring_signals.json is still required either way, for tier-2 evidence
(evidence/entity_table_map) that run_manifest.json never carries.

This is a provenance choice, not a "prefer whichever is newer" heuristic:
run_manifest.json's target_repo.commit_hash is a record of what repo state
the run that produced the *currently published* docs actually saw, which is
the thing drift should be measured against — not just "the most recent
hash available." (Prior art: fiberplane/drift, a doc-rot linter, resolves
the same kind of multi-baseline ambiguity by preferring an explicitly
stamped provenance commit over a recency-based fallback; see
claude/drift-check-manifest-baseline-research-2026-07-25.md for the full
research this design followed.) No arXiv paper was found addressing
multi-baseline selection directly for this kind of tool — noted there
rather than overclaiming precedent.

A run_manifest.json is only trustworthy as a baseline once its run reached
a terminal state: load_manifest() rejects one still at status "running"
(finalize was never called, so file_signatures is likely still init's
empty {} placeholder) or one with an empty file_signatures map even after
finalize (e.g. finalize called without --signals-file). Same principle
OpenLineage's run-lifecycle model uses for its own RunState events (START/
RUNNING are non-terminal; only COMPLETE/FAIL/ABORT are) — see
https://openlineage.io/docs/spec/run-cycle/.

Usage:
    python -m doc_engine.tools.spring_signal_scan <repo_path> --out spring_signals.json
    # ... time passes, repo changes ...
    python -m doc_engine.tools.spring_drift_check <repo_path> spring_signals.json --out drift_report.json

    # Or, to measure drift against the specific pipeline run that produced
    # the currently-published docs, rather than the raw scan:
    python -m doc_engine.tools.spring_drift_check <repo_path> spring_signals.json \\
        --manifest run_manifest.json --out drift_report.json
"""

import argparse
import json
import os
import sys
from collections import Counter

from doc_engine.scanning.support._build_signal_extract import extract_build_signals  # noqa: E402
from doc_engine.scanning.support._config_keys import extract_config_keys  # noqa: E402
from doc_engine.tools import spring_signal_scan  # noqa: E402

# Every citation ends up with exactly one of these — nothing is ever
# silently dropped from the report.
STATUS_UNCHANGED = "unchanged"
STATUS_CONFIRMED = "confirmed_still_present"
STATUS_DRIFTED = "drifted"
STATUS_FILE_DELETED = "file_deleted"
STATUS_NO_RULE_FALLBACK = "suspected_drift_content_changed_no_rule_to_recheck"
STATUS_UNKNOWN_NO_SIGNATURE = "unknown_no_prior_signature"
# The two config-file-specific outcomes below only apply to files
# spring_signal_scan.py recorded a config_key_sets entry for (schema_version
# >= 5) — everything else with no rule_id still falls back to
# STATUS_NO_RULE_FALLBACK above. See _config_keys.py's module docstring for
# why these two are worth telling apart rather than lumping both under one
# generic "changed, can't precisely recheck" status.
STATUS_CONFIG_STRUCTURE_CHANGED = "config_structure_changed"
STATUS_CONFIG_VALUES_ONLY_CHANGED = "config_values_only_changed_review_needed"

# Wire version for drift_report.json (L5 thin operator schema). Bump only on
# breaking changes; additive fields keep the same version per rel-schema-outlives-writers.
DRIFT_REPORT_SCHEMA_VERSION = 1


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


def _reject_manifest(path: str, message: str) -> None:
    print(f"error: '{path}' {message}", file=sys.stderr)
    sys.exit(1)


def _empty_signatures_are_legitimate(data) -> bool:
    target_path = data.get("target_repo", {}).get("path")
    if not target_path or not os.path.isdir(target_path):
        return False
    return not any(spring_signal_scan.dfs_walk(target_path))


def _validate_manifest_baseline(path: str, data) -> None:
    if "file_signatures" not in data:
        _reject_manifest(
            path,
            "has no 'file_signatures' field — is this a real "
            "run_manifest.json (from doc_engine.tools.run_manifest)? Not usable as a "
            "tier-1 baseline.",
        )
    if data.get("status") == "running":
        _reject_manifest(
            path,
            "has status 'running' — its pipeline run was never "
            "finalized (doc_engine.tools.run_manifest finalize was never called), so "
            "its file_signatures is likely still the empty placeholder from "
            "init and would misreport every file in the repo as newly added. "
            "Point --manifest at a manifest from after finalize, or omit "
            "--manifest to use spring_signals.json's own baseline instead.",
        )
    if data["file_signatures"]:
        return
    if _empty_signatures_are_legitimate(data):
        target_path = data.get("target_repo", {}).get("path")
        print(
            f"note: '{path}' has an empty 'file_signatures' map, but its recorded "
            f"target_repo.path ('{target_path}') genuinely has zero trackable files right "
            f"now too — treating this as a real empty-repo baseline, not a broken finalize.",
            file=sys.stderr,
        )
        return
    _reject_manifest(
        path,
        "has an empty 'file_signatures' map — finalize was "
        "called without ever recording any (e.g. no --signals-file and no "
        "repo to re-hash), so there's no real baseline to compare against. "
        "Point --manifest at a manifest with a populated file_signatures, "
        "or omit --manifest to use spring_signals.json's own baseline "
        "instead.",
    )


def load_manifest(path):
    """Load an optional run_manifest.json to use as the tier-1 file_signatures
    baseline instead of spring_signals.json's own — see the module docstring's
    "OPTIONAL --manifest" section for why this is a provenance choice, not a
    recency heuristic. Only file_signatures (plus target_repo, for the report's
    own provenance metadata) is used from it; run_manifest.json's other fields
    (stages, evidence_tag_counts, interview, ...) are irrelevant here.

    run_manifest.py's build_init_manifest() sets file_signatures to {} and
    status to "running", and only finalize_manifest() ever changes either
    (status becomes one of "complete"/"failed"/"partial"; file_signatures is
    only overwritten if finalize was actually given some). So status=="running"
    reliably means finalize never ran on this manifest at all, and an empty
    file_signatures map is *usually* a sign it was never given any (e.g.
    finalize was called without --signals-file) — treating that as a real
    baseline would silently classify every file in the repo as "added" instead
    of comparing against a real prior state (see classify_files()). This
    mirrors OpenLineage's run-lifecycle model
    (https://openlineage.io/docs/spec/run-cycle/): RUNNING is a non-terminal
    state a consumer shouldn't treat as a finished fact; only a terminal state
    (COMPLETE/FAIL/ABORT there, complete/failed/partial here) is trustworthy
    to act on.

    One legitimate exception: a repo that genuinely had zero trackable files
    at scan time also finalizes with an empty file_signatures map, and an
    "everything is newly added" report is the *correct* answer for that case,
    not a misreport. Since target_repo.path is recorded on every manifest,
    that's checked directly — if the path still exists and a fresh dfs_walk
    of it also finds zero files, the empty map is accepted as a real
    (if unusual) empty-repo baseline rather than rejected."""
    with open(path) as handle:
        data = json.load(handle)
    _validate_manifest_baseline(path, data)
    return data


def _classify_known_path(rel, old_sig, current_signatures, buckets):
    if rel not in current_signatures:
        buckets["deleted"].append(rel)
        return
    if current_signatures[rel] != old_sig:
        buckets["changed"].append(rel)
        return
    buckets["unchanged"].append(rel)


def classify_files(old_signatures, current_signatures):
    buckets = {"unchanged": [], "changed": [], "deleted": []}
    for rel, old_sig in old_signatures.items():
        _classify_known_path(rel, old_sig, current_signatures, buckets)
    added = sorted(set(current_signatures) - set(old_signatures))
    return {
        "unchanged": sorted(buckets["unchanged"]),
        "changed": sorted(buckets["changed"]),
        "deleted": sorted(buckets["deleted"]),
        "added": added,
    }


def tier1_scan(repo_path, scan_context=None):
    """Fresh sha256 per file currently in repo_path.

    When scan_context is provided, reuses its precomputed signatures (same walk
    as spring_signal_scan) instead of walking the repository again.
    """
    if scan_context is not None:
        return dict(scan_context.file_signatures)

    current = {}
    for full in spring_signal_scan.dfs_walk(repo_path):
        rel = os.path.relpath(full, repo_path).replace("\\", "/")
        try:
            current[rel] = spring_signal_scan.compute_file_signature(full)
        except OSError as exc:
            print(f"warning: could not read '{rel}': {exc}", file=sys.stderr)
    return current


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


def _entity_missing_detail(class_name):
    if class_name:
        return f"class '{class_name}' no longer matched by persistence__entity"
    return (
        "citation has no class_name to re-verify against "
        "(unexpected — treating conservatively as drift)"
    )


def _entity_table_fields_changed(citation, fresh) -> bool:
    table_changed = "table" in citation and fresh.get("table") != citation.get("table")
    source_changed = (
        "table_name_source" in citation
        and fresh.get("table_name_source") != citation.get("table_name_source")
    )
    return table_changed or source_changed


def _entity_citation_verdict(citation, fresh_entities):
    class_name = citation.get("class_name")
    fresh = fresh_entities.get(class_name) if class_name else None
    if fresh is None:
        return STATUS_DRIFTED, _entity_missing_detail(class_name)
    if _entity_table_fields_changed(citation, fresh):
        detail = f"table mapping changed: {citation.get('table')!r} -> {fresh.get('table')!r}"
        return STATUS_DRIFTED, detail
    return STATUS_CONFIRMED, None


def _recheck_entities(fresh_entity_map, group):
    """group: citations whose rule_id is persistence__entity.

    fresh_entity_map: the current entity_table_map from a fresh
    spring_signal_scan.scan() of the repo (class_name -> entry).

    Returns (results, fresh_entities): fresh_entities is the class_name ->
    {"table", "table_name_source"} map used for comparison — exposed to the
    caller so JPQL lineage provenance (_reverify_jpql_lineage_provenance) can
    reuse it without a second scan."""
    fresh_entities = dict(fresh_entity_map) if fresh_entity_map else {}
    results = []
    for source, citation in group:
        status, detail = _entity_citation_verdict(citation, fresh_entities)
        results.append(drift_result(source, citation, status, 2, detail))
    return results, fresh_entities


def _repository_missing_detail(repository_name):
    if repository_name:
        return f"repository '{repository_name}' no longer matched by persistence__repository"
    return (
        "citation has no repository name to re-verify against "
        "(unexpected — treating conservatively as drift)"
    )


def _repository_type_args_changed(citation, fresh) -> bool:
    return (
        fresh.get("entity") != citation.get("entity")
        or fresh.get("id_type") != citation.get("id_type")
    )


def _repository_citation_verdict(citation, fresh_repos):
    repository_name = citation.get("repository")
    fresh = fresh_repos.get(repository_name) if repository_name else None
    if fresh is None:
        return STATUS_DRIFTED, _repository_missing_detail(repository_name)
    if _repository_type_args_changed(citation, fresh):
        detail = (
            f"repository type args changed: <{citation.get('entity')}, {citation.get('id_type')}> "
            f"-> <{fresh.get('entity')}, {fresh.get('id_type')}>"
        )
        return STATUS_DRIFTED, detail
    return STATUS_CONFIRMED, None


def _recheck_repositories(fresh_repo_entries, group):
    """fresh_repo_entries: current persistence__repository evidence entries
    from a fresh scan. Each entry is expected to carry repository, entity, and
    id_type fields (spring_signal_scan.py adds them for persistence__repository)."""
    fresh_repos = {}
    for entry in fresh_repo_entries:
        repository_name = entry.get("repository")
        if repository_name:
            fresh_repos[repository_name] = entry

    results = []
    for source, citation in group:
        status, detail = _repository_citation_verdict(citation, fresh_repos)
        results.append(drift_result(source, citation, status, 2, detail))
    return results


def _recheck_queries(fresh_query_entries, group):
    """fresh_query_entries: current raw_queries__query evidence entries from a
    fresh scan. Each entry carries query_kind and query (spring_signal_scan.py
    extracts both from @Query annotations)."""
    fresh_counts = Counter()
    for entry in fresh_query_entries:
        fresh_counts[(entry.get("query_kind"), entry.get("query"))] += 1

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


def _recheck_generic(fresh_entries, group):
    """Fallback for every rule type without a specialized extractor. Most
    of these are single-line annotation matches (api_surface, security,
    messaging, observability, ...) where the stored `match` field is a
    meaningful shape comparison, so we compare it against the fresh scan's
    match values for the same rule in the same file."""
    fresh_counts = Counter(e.get("match") for e in fresh_entries)
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


def _raw_query_entries_with_resolved_entity(signals):
    """Single responsibility: yield every raw_queries entry whose JPQL
    lineage was resolved through an entity (lineage.resolved_via_entity,
    spring_signal_scan.py schema_version >= 6) — the only citations with a
    second provenance input beyond their own file. Native-query entries and
    out-of-scope/unavailable JPQL entries (no resolved_via_entity key at
    all — see resolve_jpql_to_lineage()) are silently skipped, not an
    oversight: they have exactly one input (their own file), already
    covered by the ordinary per-file tier-1/tier-2 loop."""
    for entry in signals.get("evidence", {}).get("raw_queries", []):
        lineage = entry.get("lineage")
        if lineage and lineage.get("resolved_via_entity"):
            yield entry


def _jpql_lineage_needs_reverify(result) -> bool:
    return result is not None and result["status"] in (STATUS_UNCHANGED, STATUS_CONFIRMED)


def _apply_jpql_lineage_verdict(result, entity, entity_file, entity_meta, fresh, entity_file_deleted):
    if fresh is None:
        result["status"] = STATUS_DRIFTED
        result["tier"] = 2
        if entity_file_deleted:
            result["detail"] = (
                f"JPQL lineage for this query was resolved via entity '{entity}', whose "
                f"defining file ({entity_file}) was deleted — lineage cannot be confirmed"
            )
        else:
            result["detail"] = (
                f"JPQL lineage for this query was resolved via entity '{entity}', which "
                f"persistence__entity no longer matches in its file ({entity_file}) — lineage cannot be confirmed"
            )
        return
    if fresh.get("table") == entity_meta.get("table"):
        result["status"] = STATUS_CONFIRMED
        result["tier"] = 2
        result["detail"] = (
            f"own file unchanged; provenance entity '{entity}' ({entity_file}) changed but its "
            f"table mapping did not, so this query's lineage is still accurate"
        )
        return
    result["status"] = STATUS_DRIFTED
    result["tier"] = 2
    result["detail"] = (
        f"JPQL lineage for this query was resolved via entity '{entity}', whose table mapping "
        f"changed in a different file ({entity_file}): {entity_meta.get('table')!r} -> {fresh.get('table')!r}"
    )


def _reverify_one_jpql_entry(
    entry,
    signals,
    fresh_entity_tables,
    changed_set,
    deleted_set,
    results_by_file_line,
) -> None:
    entity = entry["lineage"]["resolved_via_entity"]
    entity_meta = signals.get("entity_table_map", {}).get(entity)
    if entity_meta is None:
        return
    entity_file = entity_meta.get("file")
    entity_file_deleted = entity_file in deleted_set
    if entity_file not in changed_set and not entity_file_deleted:
        return
    result = results_by_file_line.get((entry.get("file"), entry.get("line")))
    if not _jpql_lineage_needs_reverify(result):
        return
    fresh = fresh_entity_tables.get(entity)
    _apply_jpql_lineage_verdict(
        result, entity, entity_file, entity_meta, fresh, entity_file_deleted
    )


def _reverify_jpql_lineage_provenance(results, signals, fresh_entity_tables, changed_set, deleted_set):
    """A JPQL citation's lineage is DERIVED from two inputs, not one: the
    query text (its own file, already handled by the per-file loop that
    produced `results`) and the entity->table mapping (a different file,
    entity_table_map[entity]["file"]). This citation is fresh only if BOTH
    inputs are unchanged — the same freshness rule every other,
    single-input citation already follows, just honestly widened for the
    one citation type that actually has a second input, rather than a
    special-cased "dependent entity" status. Mutates `results` in place;
    runs once, after the main per-file loop, so it doesn't depend on
    whether the query's file or the entity's file happened to be processed
    first (ast-grep's per-repo match order isn't guaranteed stable either —
    see spring_signal_scan.py's own JPQL-resolution pass for the same
    reasoning).

    A "changed" input file is not the only way the second input can go
    stale: DELETING (or moving, which classify_files() reports as a delete
    of the old path) the entity's file also invalidates the mapping. So the
    entity-provenance gate fires for changed_set OR deleted_set — a deleted
    entity file simply has no fresh scan, so it flows into the fresh-is-None
    -> DRIFTED branch below with a delete-specific detail. Without this, a
    JPQL query whose entity class file was deleted would come back
    "unchanged" with silently stale lineage — the exact miss this whole
    provenance pass exists to prevent, in its deletion variant.

    fresh_entity_tables: class_name -> fresh {"table", ...} dict, built as
    a side effect of the main loop's own ast-grep re-run on entity files
    already in changed_set (see _recheck_entities) — reused here rather
    than triggering a second ast-grep invocation against the same file. A
    deleted entity file is never tier-2 rechecked, so it never appears here,
    which is exactly why fresh-is-None is the correct deletion signal."""
    results_by_file_line = {(row["file"], row["line"]): row for row in results}
    for entry in _raw_query_entries_with_resolved_entity(signals):
        _reverify_one_jpql_entry(
            entry,
            signals,
            fresh_entity_tables,
            changed_set,
            deleted_set,
            results_by_file_line,
        )


def _recheck_config_keys(repo_path, file_rel, old_keys):
    """Compares a config/deployment file's stored key set (from a prior
    scan's config_key_sets) against a fresh extraction of the file as it
    exists now. Returns (status, detail), or None if the file can't be
    read (caller falls back to the generic no-rule status in that case).
    """
    full_path = os.path.join(repo_path, file_rel)
    try:
        with open(full_path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        return None

    new_keys = set(extract_config_keys(text, os.path.basename(file_rel)))
    old_keys = set(old_keys)

    if new_keys != old_keys:
        added = sorted(new_keys - old_keys)
        removed = sorted(old_keys - new_keys)
        detail = f"config key set changed: added {added or '[]'}, removed {removed or '[]'}"
        return STATUS_CONFIG_STRUCTURE_CHANGED, detail

    detail = (
        "file content changed but the config key set did not — a value changed under an "
        "unchanged key, worth a human look rather than treating as routine"
    )
    return STATUS_CONFIG_VALUES_ONLY_CHANGED, detail


def _identity_build_plugin(row):
    return (row.get("rule_id"), row.get("plugin_id"), row.get("plugin_version"))


def _identity_build_dependency(row):
    coordinate = row.get("coordinate") or {}
    return (
        row.get("rule_id"),
        row.get("configuration"),
        coordinate.get("group"),
        coordinate.get("name"),
        coordinate.get("version"),
    )


def _identity_build_module(row):
    return (row.get("rule_id"), row.get("module"))


def _identity_build_toolchain(row):
    return (row.get("rule_id"), row.get("toolchain_kind"), row.get("toolchain_value"))


def _identity_version_catalog(row):
    return (row.get("rule_id"), row.get("catalog_kind"), row.get("catalog_key"))


def _identity_fallback_match(row):
    return (row.get("rule_id"), row.get("match"))


_BUILD_SIGNAL_IDENTITY = {
    "deployment__build_plugin": _identity_build_plugin,
    "deployment__build_dependency": _identity_build_dependency,
    "deployment__build_module": _identity_build_module,
    "deployment__build_toolchain": _identity_build_toolchain,
    "deployment__version_catalog": _identity_version_catalog,
}


def _build_signal_identity(row):
    builder = _BUILD_SIGNAL_IDENTITY.get(row.get("rule_id"), _identity_fallback_match)
    return builder(row)


def _consume_identity_budget(budget, key, source, citation, missing_detail):
    if budget.get(key, 0) > 0:
        budget[key] -= 1
        return drift_result(source, citation, STATUS_CONFIRMED, 2)
    return drift_result(source, citation, STATUS_DRIFTED, 2, missing_detail)


def _recheck_build_signals(repo_path, file_rel, group):
    """Tier-2 for the synthetic build-file rule ids produced by
    _build_signal_extract.py. Reads the file, re-runs the extractor, and
    compares by structured identity (plugin_id, coordinate, module,
    toolchain, catalog key) rather than by raw match text, since the same
    line can match multiple rules and the match text is not distinctive."""
    full_path = os.path.join(repo_path, file_rel)
    try:
        with open(full_path, encoding="utf-8-sig", errors="replace") as handle:
            text = handle.read()
    except OSError as exc:
        return [
            drift_result(
                source,
                citation,
                STATUS_DRIFTED,
                2,
                f"could not read build file for re-verification: {exc}",
            )
            for source, citation in group
        ]

    fresh = extract_build_signals(file_rel, text)
    budget = dict(Counter(_build_signal_identity(row) for row in fresh))
    results = []
    for source, citation in group:
        key = _build_signal_identity(citation)
        detail = f"no fresh build signal match for {citation.get('rule_id')} identity {key}"
        results.append(_consume_identity_budget(budget, key, source, citation, detail))
    return results


def _is_build_signal_rule(rule_id: str) -> bool:
    return rule_id.startswith("deployment__build_") or rule_id == "deployment__version_catalog"


def _dispatch_tier2_rule(
    rule_id,
    group,
    *,
    repo_path,
    file_rel,
    fresh_by_rule,
    fresh_entity_map,
    results,
    fresh_entity_tables,
):
    if _is_build_signal_rule(rule_id):
        results.extend(_recheck_build_signals(repo_path, file_rel, group))
        return fresh_entity_tables
    fresh = fresh_by_rule.get(rule_id, [])
    if rule_id == "persistence__entity":
        entity_results, fresh_entity_tables = _recheck_entities(fresh_entity_map, group)
        results.extend(entity_results)
        return fresh_entity_tables
    if rule_id == "persistence__repository":
        results.extend(_recheck_repositories(fresh, group))
        return fresh_entity_tables
    if rule_id == "raw_queries__query":
        results.extend(_recheck_queries(fresh, group))
        return fresh_entity_tables
    results.extend(_recheck_generic(fresh, group))
    return fresh_entity_tables


def tier2_recheck_file(repo_path, file_rel, citations_for_file, fresh_evidence_by_file, fresh_entity_map):
    """citations_for_file: list of (source, citation), all sharing file_rel,
    all with a rule_id (caller filters out the no-rule_id ones first).

    fresh_evidence_by_file: file_rel -> list of fresh evidence entries from a
    current spring_signal_scan.scan() of the repo.

    fresh_entity_map: the fresh entity_table_map from the same scan.

    Returns (results, fresh_entity_tables) — the latter is {} unless this
    file actually has persistence__entity citations, in which case it's
    _recheck_entities' fresh_entities map passed straight through."""
    fresh_by_rule = {}
    for entry in fresh_evidence_by_file.get(file_rel, []):
        fresh_by_rule.setdefault(entry.get("rule_id"), []).append(entry)

    old_by_rule = {}
    for source, citation in citations_for_file:
        old_by_rule.setdefault(citation["rule_id"], []).append((source, citation))

    results = []
    fresh_entity_tables = {}
    for rule_id, group in old_by_rule.items():
        fresh_entity_tables = _dispatch_tier2_rule(
            rule_id,
            group,
            repo_path=repo_path,
            file_rel=file_rel,
            fresh_by_rule=fresh_by_rule,
            fresh_entity_map=fresh_entity_map,
            results=results,
            fresh_entity_tables=fresh_entity_tables,
        )
    return results, fresh_entity_tables


def _baseline_signatures_and_provenance(signals, manifest):
    """Pick tier-1 signatures + provenance from manifest or signals."""
    if manifest is not None:
        return manifest.get("file_signatures", {}), {
            "source": "run_manifest.json",
            "run_id": manifest.get("run_id"),
            "repo_path": manifest.get("target_repo", {}).get("path"),
            "commit_hash": manifest.get("target_repo", {}).get("commit_hash"),
            "dirty": manifest.get("target_repo", {}).get("dirty"),
        }
    return signals.get("file_signatures", {}), {"source": "spring_signals.json"}


def _assemble_drift_report(repo_path, signals, baseline_provenance, classification, results):
    results.sort(key=lambda row: (row["file"] or "", row["line"] or 0, row["source"]))
    status_counts = Counter(row["status"] for row in results)
    return {
        "schema_version": DRIFT_REPORT_SCHEMA_VERSION,
        "repo_path": os.path.abspath(repo_path),
        "prior_scan_repo_path": signals.get("repo_path"),
        "file_signatures_baseline": baseline_provenance,
        "file_summary": classification,
        "citations_checked": len(results),
        "status_counts": dict(status_counts),
        "results": results,
    }


def _unchanged_fast_path_results(signals):
    return [
        drift_result(source, citation, STATUS_UNCHANGED, 1)
        for source, citation in all_citations(signals)
    ]


def _index_fresh_evidence_by_file(fresh_signals):
    fresh_evidence_by_file = {}
    for _bucket_name, entries in fresh_signals.get("evidence", {}).items():
        for entry in entries:
            fresh_evidence_by_file.setdefault(entry.get("file", ""), []).append(entry)
    return fresh_evidence_by_file


def _group_citations_by_file(signals):
    citations_by_file = {}
    for source, citation in all_citations(signals):
        citations_by_file.setdefault(citation["file"], []).append((source, citation))
    return citations_by_file


def _append_uniform_status(results, citations, status, detail=None):
    for source, citation in citations:
        results.append(drift_result(source, citation, status, 1, detail))


def _recheck_citations_without_rule(repo_path, file_rel, without_rule, old_key_set, results):
    for source, citation in without_rule:
        outcome = (
            _recheck_config_keys(repo_path, file_rel, old_key_set)
            if old_key_set is not None
            else None
        )
        if outcome is not None:
            status, detail = outcome
            results.append(drift_result(source, citation, status, 1, detail))
            continue
        results.append(drift_result(
            source, citation, STATUS_NO_RULE_FALLBACK, 1,
            detail=(
                "file content changed and this citation has no rule_id to precisely recheck "
                "(filename-based evidence, e.g. config/deployment/migration match)"
            ),
        ))


def _process_changed_file_citations(
    repo_path,
    file_rel,
    citations,
    signals,
    fresh_evidence_by_file,
    fresh_entity_map,
    results,
    fresh_entity_tables,
):
    with_rule = [
        (source, citation) for source, citation in citations if citation.get("rule_id")
    ]
    without_rule = [
        (source, citation) for source, citation in citations if not citation.get("rule_id")
    ]
    old_key_set = signals.get("config_key_sets", {}).get(file_rel)
    _recheck_citations_without_rule(repo_path, file_rel, without_rule, old_key_set, results)
    if not with_rule:
        return
    file_results, file_fresh_entities = tier2_recheck_file(
        repo_path, file_rel, with_rule, fresh_evidence_by_file, fresh_entity_map
    )
    results.extend(file_results)
    fresh_entity_tables.update(file_fresh_entities)


def _process_file_citations(
    repo_path,
    file_rel,
    citations,
    *,
    deleted_set,
    unchanged_set,
    changed_set,
    signals,
    fresh_evidence_by_file,
    fresh_entity_map,
    results,
    fresh_entity_tables,
):
    if file_rel in deleted_set:
        _append_uniform_status(results, citations, STATUS_FILE_DELETED)
        return
    if file_rel in unchanged_set:
        _append_uniform_status(results, citations, STATUS_UNCHANGED)
        return
    if file_rel not in changed_set:
        # Cited but absent from both prior and fresh signature sets.
        _append_uniform_status(
            results,
            citations,
            STATUS_UNKNOWN_NO_SIGNATURE,
            detail="no prior file_signatures entry for this file to compare against",
        )
        return
    _process_changed_file_citations(
        repo_path,
        file_rel,
        citations,
        signals,
        fresh_evidence_by_file,
        fresh_entity_map,
        results,
        fresh_entity_tables,
    )


def check_drift(repo_path, signals, manifest=None):
    """manifest: optional run_manifest.json dict (see load_manifest()). When
    given, its file_signatures is the tier-1 baseline instead of signals' own
    — signals is still required regardless, for tier-2 evidence/entity_table_map
    that run_manifest.json never carries."""
    old_signatures, baseline_provenance = _baseline_signatures_and_provenance(
        signals, manifest
    )

    from doc_engine.core.context import ScanContext

    scan_context = ScanContext.build(repo_path)
    current_signatures = tier1_scan(repo_path, scan_context=scan_context)
    classification = classify_files(old_signatures, current_signatures)
    changed_set = set(classification["changed"])
    deleted_set = set(classification["deleted"])
    unchanged_set = set(classification["unchanged"])

    # Fast path: nothing moved — skip the expensive full Stage-0 rescan.
    if not changed_set and not deleted_set and not classification["added"]:
        return _assemble_drift_report(
            repo_path,
            signals,
            baseline_provenance,
            classification,
            _unchanged_fast_path_results(signals),
        )

    # Fresh Stage 0 scan of the current repo (same scanners as the prior
    # signals). Tier 2 compares citations against this bag filtered by file.
    scanners = signals.get("scanners") or ["filesystem", "ast-grep"]
    fresh_signals = spring_signal_scan.scan(
        repo_path,
        scanners=scanners,
        scan_context=scan_context,
    )
    fresh_evidence_by_file = _index_fresh_evidence_by_file(fresh_signals)
    fresh_entity_map = fresh_signals.get("entity_table_map", {})
    citations_by_file = _group_citations_by_file(signals)

    results = []
    fresh_entity_tables = {}

    for file_rel in sorted(citations_by_file):
        _process_file_citations(
            repo_path,
            file_rel,
            citations_by_file[file_rel],
            deleted_set=deleted_set,
            unchanged_set=unchanged_set,
            changed_set=changed_set,
            signals=signals,
            fresh_evidence_by_file=fresh_evidence_by_file,
            fresh_entity_map=fresh_entity_map,
            results=results,
            fresh_entity_tables=fresh_entity_tables,
        )

    # JPQL-lineage re-verify needs fresh_entity_tables fully populated.
    _reverify_jpql_lineage_provenance(
        results, signals, fresh_entity_tables, changed_set, deleted_set
    )
    return _assemble_drift_report(
        repo_path, signals, baseline_provenance, classification, results
    )


def _require_path(path: str, *, expect_dir: bool) -> None:
    ok = os.path.isdir(path) if expect_dir else os.path.isfile(path)
    kind = "directory" if expect_dir else "file"
    if not ok:
        print(f"error: not a {kind}: {path}", file=sys.stderr)
        sys.exit(1)


def _validate_drift_cli_paths(args) -> None:
    _require_path(args.repo_path, expect_dir=True)
    _require_path(args.signals_path, expect_dir=False)
    if args.manifest is not None:
        _require_path(args.manifest, expect_dir=False)


def _print_drift_summary(out_path: str, report: dict) -> None:
    file_summary = report["file_summary"]
    print(
        f"Wrote {out_path}. Tier-1 baseline: {report['file_signatures_baseline']['source']}. "
        f"Citations checked: {report['citations_checked']}. "
        f"Status counts: {report['status_counts']}. "
        f"Files: {len(file_summary['unchanged'])} unchanged, {len(file_summary['changed'])} changed, "
        f"{len(file_summary['deleted'])} deleted, {len(file_summary['added'])} added (added files carry "
        f"no prior citations, so they're informational only)."
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo_path")
    ap.add_argument("signals_path", help="prior spring_signals.json to check for drift (schema_version >= 2)")
    ap.add_argument("--out", default="drift_report.json")
    ap.add_argument(
        "--manifest", default=None,
        help="optional run_manifest.json (doc_engine.tools.run_manifest) whose file_signatures "
             "is used as the tier-1 baseline instead of signals_path's own — see module "
             "docstring's 'OPTIONAL --manifest' section. signals_path is still required, "
             "for tier-2 evidence run_manifest.json doesn't carry.",
    )
    args = ap.parse_args()
    _validate_drift_cli_paths(args)

    signals = load_signals(args.signals_path)
    manifest = load_manifest(args.manifest) if args.manifest is not None else None
    try:
        report = check_drift(args.repo_path, signals, manifest=manifest)
    except spring_signal_scan.CodeQLScannerError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    with open(args.out, "w") as handle:
        json.dump(report, handle, indent=2)
    _print_drift_summary(args.out, report)


if __name__ == "__main__":
    main()
