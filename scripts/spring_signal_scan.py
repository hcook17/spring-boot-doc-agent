#!/usr/bin/env python3
"""
spring_signal_scan.py — deterministic, AST-based evidence extraction for
Spring Boot repositories.

This exists so the doc-generation pipeline doesn't rely purely on an LLM's
read of the codebase for facts that are mechanically detectable: which
classes are controllers, which tables have JPA entities, which endpoints
are secured, which files are Dockerfiles, etc.

Java structural detection (annotations, entity/table pairing, repository
interfaces, query arguments) is delegated to ast-grep, driven by the rule
config in spring_ast_grep_rules.yml (same directory as this script). That
config's header comment explains the rule id convention and documents two
matching bugs it was rewritten to avoid (annotation-adjacency brittleness
in the entity and repository rules) — read it before changing rules here.
Filename-based detection (config/deployment/logging/migration files) stays
plain Python, since it never needed parsing in the first place.

This is still zero-build-step: ast-grep parses raw source text via
tree-sitter, no compilation or classpath needed, same trade-off the
original regex-based version made (some precision left on the table vs. a
bytecode tool like ArchUnit, in exchange for not needing a build). If you
later want higher-fidelity results (resolved inheritance, meta-annotations,
etc.), swap this stage for an ArchUnit-based scanner that runs against
compiled classes; the JSON shape below is designed so that swap doesn't
require touching the rest of the pipeline — the same reason this file was
able to move from regex to ast-grep without changing that shape either.

Output buckets map directly to documentation categories:
  api_surface       -> integrations.md, architecture.md
  outbound_clients   -> integrations.md
  messaging         -> integrations.md
  persistence       -> database.md
  raw_queries       -> database.md  (flag: JPQL vs native SQL, see note below)
  security          -> authorization.md
  configuration     -> configuration.md
  error_handling    -> troubleshooting.md
  observability     -> observability.md
  deployment        -> operations.md
  testing           -> testing.md

NOTE on raw_queries: @Query annotations without nativeQuery=true contain
JPQL, not SQL — JPQL references entity names, not table names, and tools
like SQLLineage (which parse real SQL dialects) will misparse or drop
these. This scanner tags each match with query_kind: "jpql" or "native" so
downstream stages know which queries are safe to feed to a real SQL parser
and which need the entity->table mapping resolved first (see the
entity_table_map output, built from @Table(name=...) / @Entity annotations
and Spring Data's default snake_case-of-class-name fallback). Unlike the
regex version, classification now reads the @Query annotation's own
argument list (via ast-grep's multi-meta-variable capture) rather than
guessing from "this line or the next" — so it survives arguments in either
order and annotations split across more than two lines.

NOTE on entity_table_map: each entity's NAME/TABLE now come from the text
of that entity's own class_declaration match, not from independent
first-match-in-the-whole-file regexes. The original regex version picked
the first "class X" and the first "@Table(name=...)" anywhere in the file,
which silently mismatched NAME to TABLE in any file with more than one
entity. That's fixed here as a side effect of the ast-grep rewrite, not a
separate change.

NOTE on drift detection (schema_version 2): scan()'s output now also
carries `file_signatures` (a sha256 content hash per file walked by
dfs_walk) and every evidence entry — both `evidence` bucket entries and
`entity_table_map` entries — now carries the `rule_id` that produced it
(plus, for persistence__entity, a `class_name` field on the bucket entry
so it can be correlated with its entity_table_map counterpart). Neither
field is used by anything in this file; they exist so a separate,
standalone tool (spring_drift_check.py, same directory) can later take a
repo path plus a spring_signals.json produced here and report which
citations have likely drifted — a cheap whole-repo hash filter first, then
a precise re-run of just the specific ast-grep rule behind a citation for
files that filter flags, rather than invalidating an entire file's worth of
citations because one comment changed three lines away. See
spring_drift_check.py's own module docstring for the full design. A JSON
produced by the pre-schema_version scanner (no `schema_version` key at
all) has neither field — spring_drift_check.py detects that and refuses
with a clear message rather than crashing partway through.

NOTE on SQL lineage (schema_version 3): every raw_queries entry with
query_kind == "native" now also carries a `lineage` field — best-effort
source/target table extraction via sqllineage (https://sqllineage.io),
closing the specific gap the README used to just flag and defer. This is
a SOFT dependency, unlike ast-grep: if sqllineage isn't installed, or it
can't parse this particular query (a Spring SpEL expression like
`:#{#tenant}` isn't real bind-parameter syntax and won't lex under any
SQL dialect, for instance), `lineage` degrades to
`{"available": false, "reason": "..."}` rather than raising — nothing
about the rest of the scan depends on this succeeding. Named (`:status`)
and positional (`?`, `?1`) bind parameters are substituted with a bare
`1` before parsing, since sqlfluff (sqllineage's parser backend) fails to
lex either form in any dialect, and lineage only needs table-level
structure, not bound values. The dialect used is a CLI flag (`--sql-dialect`,
default "ansi", sqllineage's own generic baseline) since this scanner has
no way to know the target database; pass the real one (e.g. "mysql",
"postgres", "oracle") for better accuracy if you know it.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

from _shared_excludes import DEFAULT_EXCLUDED_DIRS as EXCLUDED_DIRS

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RULE_FILE = os.path.join(SCRIPT_DIR, "spring_ast_grep_rules.yml")

JAVA_EXT = {".java"}
CONFIG_NAME_PATTERNS = [
    re.compile(r"^application(-[\w.]+)?\.(ya?ml|properties)$"),
    re.compile(r"^bootstrap(-[\w.]+)?\.(ya?ml|properties)$"),
]
LOGGING_CONFIG_NAMES = {"logback.xml", "logback-spring.xml", "log4j2.xml", "log4j2-spring.xml"}
MIGRATION_DIR_HINTS = ("db/migration", "db/changelog", "migrations")

NATIVE_QUERY_RE = re.compile(r"nativeQuery\s*=\s*true")
QUERY_STRING_RE = re.compile(r'"([^"]*)"')
CLASS_NAME_RE = re.compile(r"\bclass\s+(\w+)")
INTERFACE_NAME_RE = re.compile(r"\binterface\s+(\w+)")
TABLE_ARGS_RE = re.compile(r"@Table\s*\(([^)]*)\)", re.DOTALL)
TABLE_NAME_ARG_RE = re.compile(r'name\s*=\s*"([^"]+)"')
REPO_EXTENDS_RE = re.compile(
    r"(?:JpaRepository|CrudRepository|PagingAndSortingRepository|MongoRepository|ReactiveCrudRepository)"
    r"\s*<\s*([^,>]+?)\s*,\s*([^>]+?)\s*>"
)

try:
    from sqllineage.runner import LineageRunner
    _SQLLINEAGE_AVAILABLE = True
except ImportError:
    _SQLLINEAGE_AVAILABLE = False

# Spring Data JPA native queries commonly bind parameters as either named
# (:status) or positional (?, ?1) placeholders — neither is valid raw SQL
# grammar, and sqlfluff (sqllineage's parser backend) fails to lex either
# form at all, in every dialect tested, not just some. The negative
# lookbehind keeps this from mangling a literal that merely contains a
# colon next to a digit (e.g. a time literal like '12:00:00' — the
# character immediately before each of *that* string's colons is itself a
# digit, so the lookbehind excludes it; a real bind parameter's colon is
# always preceded by whitespace, an operator, '(', or ',').
NAMED_PARAM_RE = re.compile(r"(?<![\w'\"]):(\w+)")
POSITIONAL_PARAM_RE = re.compile(r"\?\d*")

SQLLINEAGE_DEFAULT_SCHEMA_PREFIX = "<default>."


def _normalize_bind_params(sql):
    """Substitute a harmless numeric literal for every named/positional bind
    parameter so sqllineage's parser can lex the query at all. Lineage
    extraction only needs table-level structure, not the bound values, so
    losing the original parameter names here is fine — this function's
    output is never surfaced anywhere, only fed to sqllineage."""
    sql = NAMED_PARAM_RE.sub("1", sql)
    sql = POSITIONAL_PARAM_RE.sub("1", sql)
    return sql


def _clean_table_name(table):
    """sqllineage reports an unqualified table as "<default>.name" (its own
    placeholder schema, not a real one this scanner has any way to confirm)
    — strip that specific prefix, but leave a genuine schema-qualified name
    (e.g. "billing.invoice") alone rather than truncating it down to just
    the table's own name."""
    s = str(table)
    if s.startswith(SQLLINEAGE_DEFAULT_SCHEMA_PREFIX):
        return s[len(SQLLINEAGE_DEFAULT_SCHEMA_PREFIX):]
    return s


def extract_sql_lineage(query_text, dialect="ansi"):
    """Best-effort source/target table extraction for one native SQL query
    string. Soft enrichment, not a load-bearing part of the scan contract:
    sqllineage is not a hard dependency the way ast-grep is, so a missing
    install, or a failure to parse this *specific* query (malformed SQL, an
    exotic dialect feature, a Spring SpEL expression that isn't real
    bind-parameter syntax), degrades to an "unavailable" result instead of
    raising. Deliberately catches the broad `Exception` rather than a
    specific sqllineage/sqlfluff exception class: sqlfluff has been
    observed to raise more than one exception type for different kinds of
    unparseable input (an InvalidSyntaxException for lexer failures, a
    bare AssertionError for at least one dialect-variant-exhaustion case),
    and this function's contract is never-raise-at-all, not merely
    never-raise-for-the-exception-types-tested-so-far.
    """
    if not _SQLLINEAGE_AVAILABLE:
        return {"available": False, "reason": "sqllineage not installed"}
    try:
        normalized = _normalize_bind_params(query_text)
        runner = LineageRunner(normalized, dialect=dialect)
        source_tables = sorted({_clean_table_name(t) for t in runner.source_tables})
        target_tables = sorted({_clean_table_name(t) for t in runner.target_tables})
        return {
            "available": True,
            "source_tables": source_tables,
            "target_tables": target_tables,
        }
    except Exception as e:
        reason = str(e).splitlines()[0][:150] if str(e) else ""
        return {"available": False, "reason": f"{type(e).__name__}: {reason}".rstrip(": ")}


def to_snake_case(name):
    """Replicates Spring Boot/Hibernate's actual default physical naming
    strategy (org.hibernate.boot.model.naming.CamelCaseToUnderscoresNamingStrategy
    — itself a verbatim port of Spring Boot's own SpringPhysicalNamingStrategy,
    per that class's own javadoc) rather than a naive "underscore before every
    capital letter" heuristic. Verified two ways, not assumed: against the real
    algorithm as published in hibernate-orm's own source (tag 5.6.7 — the
    version Spring Boot 2.7.18 pulls in), and cross-checked against
    maintainer-confirmed examples on Hibernate's own discourse forum.

    An underscore is inserted only at a lowercase-then-uppercase-then-lowercase
    transition — i.e. only where a new capitalized word both starts AND is
    itself followed by a lowercase letter. This deliberately does NOT tidy up
    runs of capital letters into acronym words the way you might expect;
    Hibernate's real default naming genuinely collapses them instead. A few
    surprising-but-real consequences worth knowing before you "fix" this again:

        SLARule    -> slarule       (not sla_rule: nothing lowercase follows
                                      the "SLA" run before "Rule" begins, and
                                      the letter immediately before that "R"
                                      is itself uppercase, so the transition
                                      rule never fires)
        APIKey     -> apikey        (same shape as SLARule)
        issueDATE  -> issuedate     (maintainer-confirmed on Hibernate's own
                                      discourse forum: a trailing run of
                                      capitals with no lowercase after it
                                      never gets split)
        issueD     -> issued        (a single trailing capital is treated
                                      exactly like a longer run — also
                                      maintainer-confirmed)
        issueDate  -> issue_date    (ordinary camelCase still splits normally)

    The previous implementation here (re.sub(r"(?<!^)(?=[A-Z])", "_",
    name).lower()) inserted an underscore before *every* capital letter
    unconditionally, which fails in the opposite direction: it splits acronym
    runs into single-letter fragments (SLARule -> s_l_a_rule) Spring/Hibernate
    would never produce. A "smarter, treat-acronyms-as-one-word" fix
    (SLARule -> sla_rule) is just as wrong for this function's purpose, even
    though it looks more sensible — it's still not what actually ends up in
    the database by default. entity_table_map exists to predict the real
    default table name, so this function's job is to match Hibernate's actual
    behavior, however quirky, not to improve on it.
    """
    buf = list(name.replace(".", "_"))
    i = 1
    while i < len(buf) - 1:
        before, current, after = buf[i - 1], buf[i], buf[i + 1]
        if before.islower() and current.isupper() and after.islower():
            buf.insert(i, "_")
            i += 1  # mirrors Java's builder.insert(i++, '_') post-increment
        i += 1
    return "".join(buf).lower()


def dfs_walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)


def compute_file_signature(path):
    """sha256 hex digest of a file's raw bytes, read in chunks so this
    doesn't load large files whole. This is the one and only place this
    hash gets computed — spring_drift_check.py imports and calls this same
    function against the current repo rather than reimplementing the
    algorithm, so scan time and drift-check time can never quietly diverge
    (e.g. one hashing raw bytes, the other decoding text first) and produce
    a hash mismatch that isn't actually about the file's content.

    Deliberately a plain content hash, not a git blob SHA: dfs_walk() (this
    file's own walk, above) reads whatever is actually on disk, uncommitted
    changes and untracked files included, and this hash needs to agree with
    that exactly. `git ls-tree`/`git hash-object` would only cover files
    tracked at HEAD, silently having nothing to compare for a new,
    not-yet-added file, and would disagree with dfs_walk's own working-tree
    view the moment there's an uncommitted edit — a repo state this scanner
    is otherwise perfectly happy to run against.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_ast_grep():
    path = shutil.which("ast-grep")
    if path is None:
        print(
            "error: the 'ast-grep' binary is not on PATH. This scanner shells out to "
            "ast-grep for all Java structural detection (see spring_ast_grep_rules.yml). "
            "Install it (e.g. `cargo install ast-grep` or `npm install -g @ast-grep/cli`, "
            "see https://ast-grep.github.io/guide/quick-start.html) and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)
    return path


def run_ast_grep(ast_grep_path, repo_path):
    cmd = [
        ast_grep_path, "scan",
        "--rule", RULE_FILE,
        "--json=compact",
        # Make exclusion depend only on EXCLUDED_DIRS below, not on whatever
        # .gitignore happens to say in a given checkout — same reasoning as
        # the rest of this script's build-independence.
        "--no-ignore", "hidden",
        "--no-ignore", "dot",
        "--no-ignore", "vcs",
        "--no-ignore", "parent",
        "--no-ignore", "global",
        "--no-ignore", "exclude",
    ]
    for d in sorted(EXCLUDED_DIRS):
        cmd += ["--globs", f"!**/{d}/**"]
    cmd.append(repo_path)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"error: ast-grep exited with status {proc.returncode}", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(proc.stdout) if proc.stdout.strip() else []
    except json.JSONDecodeError as e:
        print(f"error: could not parse ast-grep output as JSON: {e}", file=sys.stderr)
        sys.exit(1)


def _first_line_match(text):
    if not text:
        return ""
    return text.splitlines()[0].strip()[:200]


def _extract_entity(rel, text):
    """From a persistence__entity match's own text, pull the class name and,
    if present, its @Table(name=...) — checked anywhere in the annotation's
    argument list, not just as the first argument."""
    name_match = CLASS_NAME_RE.search(text)
    class_name = name_match.group(1) if name_match else None
    if class_name is None:
        return None

    table_name = None
    table_args = TABLE_ARGS_RE.search(text)
    if table_args:
        name_arg = TABLE_NAME_ARG_RE.search(table_args.group(1))
        if name_arg:
            table_name = name_arg.group(1)

    entry = {
        "file": rel,
        "table": table_name if table_name else to_snake_case(class_name),
        "table_name_source": "explicit" if table_name else "inferred-default-naming",
    }
    return class_name, entry


def _extract_repository(text):
    """From a persistence__repository match's own text, pull the interface
    name and its <Entity, Id> type arguments, if the text cleanly matches
    the expected shape (best-effort — these are bonus fields on top of the
    generic {file, line, match} entry, not load-bearing for the contract)."""
    name_match = INTERFACE_NAME_RE.search(text)
    entity_match = REPO_EXTENDS_RE.search(text)
    extra = {}
    if name_match:
        extra["repository"] = name_match.group(1)
    if entity_match:
        extra["entity"] = entity_match.group(1).strip()
        extra["id_type"] = entity_match.group(2).strip()
    return extra


def _extract_query(multi_args):
    """Classify a @Query(...) match as jpql/native and pull the query
    string, from the annotation's own argument fragments (multi.ARGS) —
    robust to argument order and to the annotation splitting across more
    than two lines, unlike the old this-line-or-next-line regex check."""
    joined = " ".join(frag.get("text", "") for frag in multi_args)
    query_kind = "native" if NATIVE_QUERY_RE.search(joined) else "jpql"
    query_text = None
    m = QUERY_STRING_RE.search(joined)
    if m:
        query_text = m.group(1)
    return query_kind, query_text


def scan(repo_path, sql_dialect="ansi"):
    buckets = {
        "api_surface": [], "outbound_clients": [], "messaging": [],
        "persistence": [], "raw_queries": [], "security": [],
        "configuration": [], "error_handling": [], "observability": [],
        "deployment": [], "testing": [],
    }
    entity_table_map = {}
    files_scanned = {"java": 0, "config": 0, "deployment": 0, "other_relevant": 0}
    file_signatures = {}

    # Pass 1 (plain Python, no parsing): filename-based buckets, plus a
    # java-file count for files_scanned. Unlike the regex-era version this
    # no longer needs to read file contents at all for classification —
    # ast-grep reads Java source itself in pass 2 — but it does now read
    # every file once for its content signature (see compute_file_signature
    # above), unconditionally, before the classification below, so
    # file_signatures covers exactly the set of files dfs_walk visits —
    # the same set drift-check tooling will later re-walk and re-hash.
    for full in dfs_walk(repo_path):
        rel = os.path.relpath(full, repo_path).replace("\\", "/")
        name = os.path.basename(full)
        _, ext = os.path.splitext(name)

        try:
            file_signatures[rel] = compute_file_signature(full)
        except OSError as e:
            # A single unreadable file (broken symlink, permissions) is not
            # a reason to abandon the whole scan — just leave it out of
            # file_signatures. Downstream drift-check tooling treats a
            # citation whose file has no stored signature as "can't verify"
            # rather than silently assuming "unchanged".
            print(f"warning: could not read '{rel}' to compute its content signature: {e}", file=sys.stderr)

        if ext in JAVA_EXT:
            files_scanned["java"] += 1
            continue

        if any(p.match(name) for p in CONFIG_NAME_PATTERNS):
            files_scanned["config"] += 1
            buckets["configuration"].append({"file": rel, "match": "config file"})
            continue

        if name in LOGGING_CONFIG_NAMES:
            files_scanned["other_relevant"] += 1
            buckets["observability"].append({"file": rel, "match": "logging config file"})
            continue

        if name.startswith("Dockerfile") or re.match(r"docker-compose.*\.ya?ml$", name):
            files_scanned["deployment"] += 1
            buckets["deployment"].append({"file": rel, "match": "container/compose file"})
            continue

        if ext in (".yml", ".yaml") and any(
            seg in rel.split("/") for seg in ("k8s", "helm", "charts", "deploy", "deployment", ".github")
        ):
            files_scanned["deployment"] += 1
            buckets["deployment"].append({"file": rel, "match": "deployment manifest"})
            continue

        if any(hint in rel for hint in MIGRATION_DIR_HINTS):
            files_scanned["other_relevant"] += 1
            buckets["persistence"].append({"file": rel, "match": "migration script"})
            continue

    # Pass 2: everything Java-structural, via ast-grep.
    ast_grep_path = find_ast_grep()
    matches = run_ast_grep(ast_grep_path, repo_path)

    seen = set()  # (file, line, ruleId) -> collapse same AST-node-kind hits that land on one line
    for m in matches:
        rel = os.path.relpath(m["file"], repo_path).replace("\\", "/")
        line = m["range"]["start"]["line"] + 1
        text = m.get("text", "")
        rule_id = m["ruleId"]
        match_str = _first_line_match(text)

        dedup_key = (rel, line, rule_id)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        if rule_id == "persistence__entity":
            extracted = _extract_entity(rel, text)
            if extracted is None:
                continue
            class_name, map_entry = extracted
            # rule_id + match let drift-check tooling re-verify this exact
            # citation later (re-run persistence__entity against just this
            # file, re-extract, compare) without guessing which rule
            # produced it. class_name on the bucket-side entry (below) is
            # what lets that same tooling correlate the two parallel
            # representations of one entity match — entity_table_map has no
            # `line`/`match` of its own to key off, and the bucket entry has
            # no `table`/`table_name_source` — without class_name on the
            # bucket entry, the two can't be tied back together.
            map_entry["rule_id"] = rule_id
            map_entry["match"] = match_str
            entity_table_map[class_name] = map_entry
            buckets["persistence"].append({
                "file": rel, "line": line, "match": match_str,
                "rule_id": rule_id, "class_name": class_name,
            })
            continue

        bucket, _, _subkind = rule_id.partition("__")
        if bucket not in buckets:
            # Defensive: a rule id that doesn't map to a known bucket shouldn't
            # silently vanish or crash the whole scan.
            print(f"warning: ast-grep rule id '{rule_id}' has no matching evidence bucket, skipping", file=sys.stderr)
            continue

        # rule_id travels with every entry (not just persistence__entity,
        # above) so drift-check tooling always knows which specific
        # ast-grep rule to re-run for a precise recheck, rather than
        # guessing from the bucket name — a bucket like `persistence` mixes
        # rule_id-bearing entries with plain-Python filename matches (the
        # migration-script entries appended in pass 1 above) that have no
        # rule_id at all, deliberately: there's no rule to re-run for those.
        entry = {"file": rel, "line": line, "match": match_str, "rule_id": rule_id}

        if rule_id == "raw_queries__query":
            multi_args = m.get("metaVariables", {}).get("multi", {}).get("ARGS", [])
            query_kind, query_text = _extract_query(multi_args)
            entry["query_kind"] = query_kind
            if query_text is not None:
                entry["query"] = query_text
                if query_kind == "native":
                    entry["lineage"] = extract_sql_lineage(query_text, dialect=sql_dialect)
        elif rule_id == "persistence__repository":
            entry.update(_extract_repository(text))

        buckets[bucket].append(entry)

    # ast-grep may use multiple threads internally (-j/--threads defaults to
    # a heuristic thread count), so match order isn't guaranteed stable
    # across runs even when the underlying file set hasn't changed. Sort
    # each bucket so the output — and any diff of it — is deterministic.
    for bucket in buckets.values():
        bucket.sort(key=lambda e: (e["file"], e.get("line", 0)))

    return {
        "schema_version": 3,
        "repo_path": os.path.abspath(repo_path),
        "files_scanned": files_scanned,
        "entity_table_map": entity_table_map,
        "evidence": buckets,
        "file_signature_algorithm": "sha256",
        "file_signatures": file_signatures,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo_path")
    ap.add_argument("--out", default="spring_signals.json")
    ap.add_argument(
        "--sql-dialect", default="ansi",
        help="SQL dialect for native-query lineage extraction via sqllineage "
             "(only applies to raw_queries entries with query_kind=='native'). "
             "Defaults to 'ansi', sqllineage's own generic baseline, since this "
             "scanner has no way to know the target database. Pass the real "
             "one (e.g. 'mysql', 'postgres', 'oracle', 'sqlite', 'tsql') for "
             "better accuracy if you know it.",
    )
    args = ap.parse_args()

    if not os.path.isdir(args.repo_path):
        print(f"error: not a directory: {args.repo_path}", file=sys.stderr)
        sys.exit(1)

    result = scan(args.repo_path, sql_dialect=args.sql_dialect)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)

    counts = {k: len(v) for k, v in result["evidence"].items()}
    print(f"Wrote {args.out}. Files scanned: {result['files_scanned']}. "
          f"Entities found: {len(result['entity_table_map'])}. "
          f"Evidence counts: {counts}")


if __name__ == "__main__":
    main()
