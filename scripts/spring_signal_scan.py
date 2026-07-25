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
  references        -> consumed by file-summarizer for cross-group relationship-
                        finding; not written directly into any of the 14 output files

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
order and annotations split across more than two lines. As of
schema_version 5, the bounded common case of a single-entity JPQL FROM
clause is resolved to real lineage via resolve_jpql_to_lineage(), not left
as raw text forever — see that function's own docstring for exactly what's
in and out of scope. (Native-query lineage landed earlier, at
schema_version 3 — see the SQL lineage note below. The two are separate
releases; JPQL resolution reuses that machinery but did not ship with it.)

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

query_kind == "jpql" entries also carry a `lineage` field, resolved via
resolve_jpql_to_lineage() (a bounded rewrite-to-SQL step feeding into the
same extract_sql_lineage() above) rather than left unattempted — but only
for the single-entity, no-join, no-association-traversal, no-JPQL-function
common case; anything outside that scope degrades to the same
`{"available": false, "reason": "..."}` shape, not a crash or a wrong
answer. See resolve_jpql_to_lineage()'s own docstring for the exact
boundary and why no broader JPQL-to-SQL translator was built or adopted
(no published research or usable open-source tooling exists for this —
verified 2026-07-25, see claude/session-log.md).

NOTE on redaction zones (schema_version 4): output now also carries
`redaction_zones`, a {file: [{"line", "heuristic"}, ...]} map of lines in
configuration/deployment files that look like they carry a real credential
(see _secret_heuristics.py, same directory, for the detection rules and
why this is heuristic rather than exhaustive). This never carries the
matched value itself, only its location and which heuristic fired — the
scanner stays exactly as clean as it was before (never reads config
*values* into its own output), it just now also flags *where* a later
stage should be careful. Closes the gap CONSTRAINTS.md's "Secret/credential
leakage" entry describes: Stage 1 (file-summarizer) reads full file
content directly and had no signal telling it which lines not to
transcribe into its own output.

NOTE on JPQL lineage provenance (schema_version 6): a `jpql`-kind
raw_queries entry whose `lineage` resolved successfully now also carries
`lineage.resolved_via_entity` — the entity class name entity_table_map was
consulted through. This exists for spring_drift_check.py: a JPQL
citation's lineage has a cross-file dependency on the entity's own file
(its @Table(name=...)), which the per-file tier-1/tier-2 model otherwise
can't see — the query's own file doesn't change just because the entity's
table mapping did. See spring_drift_check.py's
_raw_query_entries_with_resolved_entity() and _reverify_jpql_lineage_provenance().

NOTE on config key sets (schema_version 5): output now also carries
`config_key_sets`, a {file: [dotted.key.path, ...]} map for configuration/
deployment files (see _config_keys.py for the mechanical, no-YAML-
dependency extraction). Key *names* only, never values — same posture as
redaction_zones above. This exists for spring_drift_check.py to tell apart
two very different reasons a config file's content hash might change on
re-scan: the key set itself changed (added/removed a property — an
expected, structural evolution) versus the key set staying identical while
the file's hash still changed (the only way that happens is a *value*
changed under an unchanged key — worth flagging for review rather than
treating as routine, in a setup where these files are checked-in
placeholders and real values are injected by an external service at
deploy time, per the framing this check was built for).
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

from _shared_excludes import DEFAULT_EXCLUDED_DIRS as EXCLUDED_DIRS, load_gitignore_spec
from _secret_heuristics import scan_text_for_secrets
from _config_keys import extract_config_keys

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

# Bounded JPQL resolution (schema_version 5 — a later release than the
# native-query lineage above, whose machinery it reuses; see
# resolve_jpql_to_lineage()'s own docstring for the full scope statement).
# Matches "FROM <Entity> <alias>", optionally with an
# "AS" keyword — deliberately anchored to exactly one FROM target: a
# comma-separated or JOINed multi-entity FROM clause won't match this
# pattern the way a single-entity one does, which is how multi-entity
# queries fall through to "out of scope" below rather than being
# (wrongly) partially resolved.
JPQL_FROM_RE = re.compile(r"\bFROM\s+(\w+)\s+(?:AS\s+)?(\w+)\b", re.IGNORECASE)
# An explicit JOIN keyword (including "JOIN FETCH") always means more than
# one entity is involved, even though JPQL_FROM_RE above still matches
# exactly once for "FROM Invoice i JOIN i.customer c" — the join target
# isn't itself introduced by a second FROM, so it has to be caught
# separately, before the single-FROM-match check below can be trusted to
# mean "genuinely single-entity."
JPQL_JOIN_RE = re.compile(r"\bJOIN\b", re.IGNORECASE)
# JPQL-only functions with no SQL equivalent a rewritten-to-SQL string could
# ever satisfy — not an attempt at a general JPQL grammar, just the specific
# functions that would otherwise silently produce wrong (not just
# unavailable) lineage if naively passed through to a SQL parser.
JPQL_FUNCTION_RE = re.compile(r"\b(SIZE|KEY|VALUE|INDEX|TYPE)\s*\(", re.IGNORECASE)


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


def resolve_jpql_to_lineage(jpql_text, entity_table_map, dialect="ansi"):
    """Best-effort lineage for the narrow slice of JPQL this scanner can
    safely rewrite to real SQL: a single-entity `FROM <Entity> <alias>`
    clause, no joins, no association-traversal through the alias (e.g.
    `u.orders.total`), none of JPQL's relationship-only functions (SIZE,
    KEY, VALUE, INDEX, TYPE — no SQL equivalent exists for these, so
    passing them through would risk a wrong answer, not just an
    unavailable one). Resolves the entity name to a table name via
    entity_table_map (built earlier in scan() from @Entity/@Table
    annotations), strips the alias prefix from field references, and
    hands the rewritten string to extract_sql_lineage() — no independent
    SQL-parsing logic here, just enough rewriting to make an existing SQL
    parser applicable.

    No published academic or open-source precedent exists for general
    JPQL/HQL-to-SQL lineage translation (verified 2026-07-25: an arXiv
    search turned up nothing on-point, and sqllineage's own tracker has an
    open, unresolved request for exactly this — reata/sqllineage#461).
    This function's scope is deliberately narrow rather than attempting a
    general translator: the "resolve identifiers against a pre-built
    entity metamodel, then lower to SQL" shape mirrors how Hibernate's own
    SQM pipeline resolves JPQL at a much larger scope, so the *approach*
    has precedent even though no *tool* does.

    Explicitly, permanently out of scope, not just "not yet handled" —
    each of these needs more than a rewrite to resolve correctly, so
    resolving them wrong would be worse than reporting unavailable:
      - Multi-entity FROM (joins, comma-separated entities).
      - Association-traversal paths through the alias (`u.orders.total`).
      - `@Entity(name=...)` overrides: entity_table_map is keyed by Java
        class name, so a query using an overridden JPQL entity name
        legitimately won't resolve — a correct "not found", not a wrong
        resolution, since this scanner doesn't currently extract the
        `name=` argument of @Entity separately from @Table's.
      - Polymorphic FROM (naming a superclass/interface — inherently
        multi-table under JOINED/TABLE_PER_CLASS inheritance).
      - Embedded/composite keys (`@EmbeddedId`/`@IdClass` field paths like
        `i.id.customerId`) — needs embeddable-aware path resolution, not a
        flat class-name lookup.

    Returns the same shape extract_sql_lineage() does — {"available":
    True, "source_tables": [...], "target_tables": [...]} or
    {"available": False, "reason": "..."} — so callers don't need to
    distinguish "JPQL degrade" from "native SQL degrade"."""
    if JPQL_JOIN_RE.search(jpql_text):
        return {
            "available": False,
            "reason": "multi-entity or unparseable FROM clause, out of scope for the bounded JPQL resolver",
        }
    matches = list(JPQL_FROM_RE.finditer(jpql_text))
    if len(matches) != 1:
        return {
            "available": False,
            "reason": "multi-entity or unparseable FROM clause, out of scope for the bounded JPQL resolver",
        }
    if JPQL_FUNCTION_RE.search(jpql_text):
        return {
            "available": False,
            "reason": "uses a JPQL-only relationship function (SIZE/KEY/VALUE/INDEX/TYPE), out of scope",
        }

    from_match = matches[0]
    entity_name, alias = from_match.group(1), from_match.group(2)

    # A second, comma-separated entity right after the first doesn't repeat
    # the FROM keyword ("FROM Invoice i, Customer c ..."), so it wouldn't
    # otherwise be caught by the single-FROM-match check above.
    if jpql_text[from_match.end():].lstrip().startswith(","):
        return {
            "available": False,
            "reason": "multi-entity or unparseable FROM clause, out of scope for the bounded JPQL resolver",
        }

    traversal_re = re.compile(r"\b" + re.escape(alias) + r"\.\w+\.\w+")
    if traversal_re.search(jpql_text):
        return {
            "available": False,
            "reason": "association-traversal path through the entity alias, out of scope",
        }

    map_entry = entity_table_map.get(entity_name)
    if map_entry is None:
        return {
            "available": False,
            "reason": f"entity '{entity_name}' not found in entity_table_map — unresolved rather than "
                      "guessed (possibly an @Entity(name=...) override this scanner doesn't capture)",
        }

    rewritten = jpql_text[:from_match.start()] + f"FROM {map_entry['table']}" + jpql_text[from_match.end():]
    alias_prefix_re = re.compile(r"\b" + re.escape(alias) + r"\.")
    rewritten = alias_prefix_re.sub("", rewritten)

    result = extract_sql_lineage(rewritten, dialect=dialect)
    if result["available"]:
        # Records the dependency, not just the outcome: spring_drift_check.py
        # needs to know a JPQL citation's lineage came from *this* entity so
        # it can flag the citation as possibly stale if that entity's own
        # table mapping later changes in a different file — a cross-file
        # dependency the per-file tier-1/tier-2 model can't otherwise see.
        result["resolved_via_entity"] = entity_name
    return result


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


def dfs_walk(root, gitignore_spec=None):
    """gitignore_spec, if given, is a pathspec.PathSpec (see
    _shared_excludes.load_gitignore_spec) additionally consulted against
    each entry's path relative to root — opt-in, off by default, on top
    of the hardcoded EXCLUDED_DIRS floor, not a replacement for it."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith("."))
        if gitignore_spec is not None:
            dirnames[:] = [
                d for d in dirnames
                if not gitignore_spec.match_file(os.path.relpath(os.path.join(dirpath, d), root).replace("\\", "/") + "/")
            ]
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if gitignore_spec is not None and gitignore_spec.match_file(os.path.relpath(full, root).replace("\\", "/")):
                continue
            yield full


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


class AstGrepNotFoundError(RuntimeError):
    """Raised by find_ast_grep() when the binary isn't on PATH.

    A plain Exception subclass on purpose, not a sys.exit(1) call directly:
    when scan() runs inside unittest's setUpClass (test_spring_signal_scan.py,
    test_capacity_preflight.py, test_spring_drift_check.py all call scan()
    there), unittest's _handleClassSetUp only catches Exception, not
    BaseException — SystemExit is a BaseException, so raising it here used to
    propagate straight through and kill the whole test process with no
    per-class error and no "Ran N tests" summary line, rather than being
    reported as a normal setUpClass failure for just that one class. CLI
    entry points (main() in this file, spring_drift_check.py, and
    capacity_preflight.py) catch this explicitly and print the same
    stderr message + sys.exit(1) as before, so command-line behavior is
    unchanged."""


def find_ast_grep():
    path = shutil.which("ast-grep")
    if path is None:
        raise AstGrepNotFoundError(
            "error: the 'ast-grep' binary is not on PATH. This scanner shells out to "
            "ast-grep for all Java structural detection (see spring_ast_grep_rules.yml). "
            "Install it (e.g. `cargo install ast-grep` or `npm install -g @ast-grep/cli`, "
            "see https://ast-grep.github.io/guide/quick-start.html) and re-run."
        )
    return path


def run_ast_grep(ast_grep_path, repo_path, respect_gitignore=False):
    cmd = [
        ast_grep_path, "scan",
        "--rule", RULE_FILE,
        "--json=compact",
        # Make exclusion depend only on EXCLUDED_DIRS below, not on whatever
        # .gitignore happens to say in a given checkout — same reasoning as
        # the rest of this script's build-independence. When respect_gitignore
        # is set, "vcs" is omitted below so ast-grep's own native .gitignore
        # handling takes over for that one category — no need to reimplement
        # gitignore matching for the ast-grep subprocess call itself. Note
        # this only actually does anything inside a real VCS root (a .git
        # directory present) — same as ripgrep's underlying `ignore` crate,
        # a standalone .gitignore with no .git next to it is invisible to
        # this. Real target repos for this plugin are checkouts, so this
        # isn't a practical gap, but it's why the Python-side dfs_walk
        # gitignore_spec matching (which has no such requirement) is the
        # one actually doing the work in a bare-directory scan.
        "--no-ignore", "hidden",
        "--no-ignore", "dot",
        "--no-ignore", "parent",
        "--no-ignore", "global",
        "--no-ignore", "exclude",
    ]
    if not respect_gitignore:
        cmd += ["--no-ignore", "vcs"]
    for d in sorted(EXCLUDED_DIRS):
        cmd += ["--globs", f"!**/{d}/**"]
    cmd.append(repo_path)

    # encoding= is explicit rather than left to text=True's default, which is
    # the *locale* codec — cp1252 on a default Windows install. ast-grep emits
    # UTF-8 JSON that echoes matched source text, and that text lands in every
    # evidence row's "match" field (see the buckets appends below), so a
    # locale-decoded read corrupts evidence two different ways: a character
    # whose UTF-8 bytes are all defined in cp1252 (é, 日, emoji) decodes to
    # silent mojibake that flows on into cited documentation, and one whose
    # bytes include 0x81/0x8D/0x8F/0x90/0x9D (Cyrillic 'с' is d1 81) raises
    # UnicodeDecodeError and takes down the whole scan. errors="replace" so a
    # genuinely undecodable byte degrades one match instead of the run.
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
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


def _process_config_deployment_file(full, rel, redaction_zones, config_key_sets):
    """Runs both config-file heuristics — _secret_heuristics.py's value
    scan and _config_keys.py's key-path extraction — against one
    configuration/deployment file, reading it once rather than twice.
    Only called for files already classified into the "configuration"/
    "deployment" buckets below — the same file set, not a second
    independent walk.

    redaction_zones never carries the matched value, only line + heuristic
    name (see _secret_heuristics.py). config_key_sets carries key *names*
    only — those are the config's schema, not a secret in their own right —
    used by spring_drift_check.py to tell "the config's shape changed"
    (structural, expected) apart from "the same keys now hold different
    values" (see _config_keys.py's docstring for why that distinction
    matters more than value content in a deploy-time-injected-secrets
    setup).
    """
    try:
        # utf-8-sig, not utf-8: a BOM-prefixed config file is common in
        # Windows-authored repos, and plain utf-8 decodes the BOM to a literal
        # ﻿ that survives into the text. ﻿ is not matched by \s, so
        # the ^\s*-anchored regexes downstream (_config_keys.py's
        # _YAML_KEY_LINE_RE, _secret_heuristics.py's KEY_VALUE_LINE_RE) fail on
        # the first line only — silently dropping that file's first config key
        # and, worse, never flagging a credential sitting on line 1.
        with open(full, encoding="utf-8-sig", errors="ignore") as f:
            text = f.read()
    except OSError:
        return  # same posture as compute_file_signature above: skip, don't abort the scan

    hits = scan_text_for_secrets(text)
    if hits:
        redaction_zones[rel] = hits

    keys = extract_config_keys(text, os.path.basename(rel))
    if keys:
        config_key_sets[rel] = keys


def scan(repo_path, sql_dialect="ansi", respect_gitignore=False):
    gitignore_spec = load_gitignore_spec(repo_path) if respect_gitignore else None

    buckets = {
        "api_surface": [], "outbound_clients": [], "messaging": [],
        "persistence": [], "raw_queries": [], "security": [],
        "configuration": [], "error_handling": [], "observability": [],
        "deployment": [], "testing": [], "references": [],
    }
    entity_table_map = {}
    files_scanned = {"java": 0, "config": 0, "deployment": 0, "other_relevant": 0}
    file_signatures = {}
    redaction_zones = {}
    config_key_sets = {}

    # Pass 1 (plain Python, no parsing): filename-based buckets, plus a
    # java-file count for files_scanned. Unlike the regex-era version this
    # no longer needs to read file contents at all for classification —
    # ast-grep reads Java source itself in pass 2 — but it does now read
    # every file once for its content signature (see compute_file_signature
    # above), unconditionally, before the classification below, so
    # file_signatures covers exactly the set of files dfs_walk visits —
    # the same set drift-check tooling will later re-walk and re-hash.
    for full in dfs_walk(repo_path, gitignore_spec=gitignore_spec):
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
            _process_config_deployment_file(full, rel, redaction_zones, config_key_sets)
            continue

        if name in LOGGING_CONFIG_NAMES:
            files_scanned["other_relevant"] += 1
            buckets["observability"].append({"file": rel, "match": "logging config file"})
            continue

        if name.startswith("Dockerfile") or re.match(r"docker-compose.*\.ya?ml$", name):
            files_scanned["deployment"] += 1
            buckets["deployment"].append({"file": rel, "match": "container/compose file"})
            _process_config_deployment_file(full, rel, redaction_zones, config_key_sets)
            continue

        if ext in (".yml", ".yaml") and any(
            seg in rel.split("/") for seg in ("k8s", "helm", "charts", "deploy", "deployment", ".github")
        ):
            files_scanned["deployment"] += 1
            buckets["deployment"].append({"file": rel, "match": "deployment manifest"})
            _process_config_deployment_file(full, rel, redaction_zones, config_key_sets)
            continue

        if any(hint in rel for hint in MIGRATION_DIR_HINTS):
            files_scanned["other_relevant"] += 1
            buckets["persistence"].append({"file": rel, "match": "migration script"})
            continue

    # Pass 2: everything Java-structural, via ast-grep.
    ast_grep_path = find_ast_grep()
    matches = run_ast_grep(ast_grep_path, repo_path, respect_gitignore=respect_gitignore)

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
            # This map is keyed by simple class name alone, so two @Entity
            # classes in different packages collide. Plain last-write-wins
            # would hand the collision to ast-grep's match order, which isn't
            # stable across runs (see the threading note below) — the same
            # input tree could report a different `table` for the same key on
            # a re-scan. Resolve on lowest file path instead: it depends only
            # on the input, and drift-check re-verification of this citation
            # then has a fixed target rather than a coin flip.
            prior = entity_table_map.get(class_name)
            if prior is None or map_entry["file"] < prior["file"]:
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

    # JPQL lineage resolution happens in its own pass, after the match loop
    # above finishes, not inline alongside the native-query branch: it needs
    # entity_table_map fully populated, and ast-grep's match order (see the
    # threading note below) gives no guarantee that a class's
    # persistence__entity match is processed before a raw_queries__query
    # match elsewhere that references it.
    for entry in buckets["raw_queries"]:
        if entry.get("query_kind") == "jpql" and entry.get("query") is not None:
            entry["lineage"] = resolve_jpql_to_lineage(entry["query"], entity_table_map, dialect=sql_dialect)

    # ast-grep may use multiple threads internally (-j/--threads defaults to
    # a heuristic thread count), so match order isn't guaranteed stable
    # across runs even when the underlying file set hasn't changed. Sort
    # each bucket so the output — and any diff of it — is deterministic.
    for bucket in buckets.values():
        bucket.sort(key=lambda e: (e["file"], e.get("line", 0)))

    # entity_table_map is populated inside that same match loop, so its key
    # order follows the same unstable ast-grep match order the buckets are
    # sorted to escape. Sorting it matters for a reason the buckets' comment
    # doesn't state: compute_file_signature() and every downstream hash read
    # raw bytes, so an unsorted map means identical scans of an unchanged repo
    # serialize to different bytes, and a hash of spring_signals.json can't be
    # used to assert anything.
    entity_table_map = dict(sorted(entity_table_map.items()))

    return {
        "schema_version": 6,
        "repo_path": os.path.abspath(repo_path),
        "files_scanned": files_scanned,
        "entity_table_map": entity_table_map,
        "evidence": buckets,
        "file_signature_algorithm": "sha256",
        "file_signatures": file_signatures,
        "redaction_zones": redaction_zones,
        "config_key_sets": config_key_sets,
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
    ap.add_argument("--respect-gitignore", action="store_true", default=False,
                     help="Additionally exclude paths matched by the repo's own .gitignore, "
                          "on top of the hardcoded EXCLUDED_DIRS floor (default: off; requires "
                          "the pathspec library for the Python-side walk; ast-grep's own native "
                          "gitignore handling is used for the ast-grep subprocess call)")
    args = ap.parse_args()

    if not os.path.isdir(args.repo_path):
        print(f"error: not a directory: {args.repo_path}", file=sys.stderr)
        sys.exit(1)

    try:
        result = scan(args.repo_path, sql_dialect=args.sql_dialect, respect_gitignore=args.respect_gitignore)
    except AstGrepNotFoundError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)

    counts = {k: len(v) for k, v in result["evidence"].items()}
    redaction_hit_count = sum(len(hits) for hits in result["redaction_zones"].values())
    print(f"Wrote {args.out}. Files scanned: {result['files_scanned']}. "
          f"Entities found: {len(result['entity_table_map'])}. "
          f"Evidence counts: {counts}. "
          f"Redaction zones flagged: {redaction_hit_count} line(s) across "
          f"{len(result['redaction_zones'])} file(s). "
          f"Config key sets recorded for {len(result['config_key_sets'])} file(s).")


if __name__ == "__main__":
    main()
