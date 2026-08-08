"""
_secret_heuristics.py — shared, deterministic secret-shaped-value detection.

Single source of truth for "does this line look like it's carrying a real
credential", the same role _shared_excludes.py plays for excluded
directories (IMPLEMENTATION_HANDOFF.md item 1: two independently-maintained
copies of the same fact is a known drift risk in this project specifically).
Two callers share this module rather than each growing their own pattern
list:

  - spring_signal_scan (``python -m doc_engine.tools.spring_signal_scan``):
    flags line numbers in configuration/deployment files as `redaction_zones`
    evidence, so Stage 1 (file-summarizer) has a mechanical signal for which
    lines not to transcribe (see `adapters/claude/agents/file-summarizer.md`
    and CONSTRAINTS.md's "Secret/credential leakage" entry for the gap this
    closes).
  - check_no_secrets_leaked (``python -m doc_engine.tools.check_no_secrets_leaked``):
    re-applies the exact same heuristics to a
    completed run's own output artifacts (summaries.json, docs/*.md) as a
    deterministic defense-in-depth check — an LLM subagent's compliance
    with a prompt instruction is not a guarantee, so this project's own
    standing "mechanical wherever possible, don't just trust it" posture
    (spring_drift_check.py, verify_llms_docs.py, test_pipeline_stages.py's
    citation-resolution check) applies here too.

WHAT THIS DOES NOT TRY TO DO
This is a heuristic, not a secret scanner with a security-vendor's rule
set (no entropy scoring, no per-provider key-format catalog beyond the two
unambiguous patterns below). False positives (flagging a line that isn't
actually a secret) are the safe failure direction and are expected — a
line like `password_hint_visible: true` will get flagged even though it
carries no credential. False negatives (a real secret under a key name
this heuristic doesn't recognize, or with no recognizable shape at all)
are possible and not claimed to be caught. Sized to the actual leak vector
CONSTRAINTS.md names — hardcoded literals in Spring config files — not a
general-purpose credential-scanning product.

One further stated limit specific to check_no_secrets_leaked.py's reuse of
this module against generated prose (not raw config files): the key-name
heuristic only fires when the secret-shaped key is the line's own key —
"password: hunter2literal" (a reproduced config snippet, key intact) is
caught, but a value transcribed into a sentence under an unrelated key
("summary": "...configures the password as hunter2literal...") is not,
since there is no local key token to match against. Only the two
key-agnostic HIGH_CONFIDENCE_PATTERNS (AWS access key IDs, PEM blocks)
catch a value regardless of the surrounding context.
"""

import re

# Key names commonly used for credentials in application*.yml/properties,
# Dockerfiles, and compose/k8s manifests. Case-insensitive; matched against
# the token immediately before a `:` or `=` separator.
SECRET_KEY_NAME_RE = re.compile(
    r"(password|passwd|pwd|secret|token|api[-_]?key|access[-_]?key|"
    r"private[-_]?key|client[-_]?secret|credential|auth[-_]?token)",
    re.IGNORECASE,
)

# A value that is itself an indirection to somewhere else (an env var, a
# platform secret store, an unfilled template) rather than a literal
# credential checked into the repo — doc-taxonomy.md's configuration.md
# notes already ask for exactly this to be written up as "value supplied
# at deploy time, not in repo", so a line shaped this way is the *safe*
# case, not a leak, and should not be flagged.
PLACEHOLDER_VALUE_RE = re.compile(
    r"^\s*(\$\{[^}]*\}|<[^>]*>|CHANGEME|CHANGE_ME|xxx+|\*+|)\s*$",
    re.IGNORECASE,
)

# A `key: value` / `key=value` / `key: "value"` line, permissive enough to
# cover YAML and .properties both.
KEY_VALUE_LINE_RE = re.compile(r"^\s*[\"']?([\w.\-]+)[\"']?\s*[:=]\s*(.+?)\s*$")

# One matching pair of surrounding quotes, which the line regex above strips
# from the KEY but not from the VALUE.
QUOTED_VALUE_RE = re.compile(r"^([\"'])(.*)\1$", re.DOTALL)


def _unquote(value):
    """Strip one matching pair of surrounding quotes.

    Without this, PLACEHOLDER_VALUE_RE anchors against the quote characters
    and never matches: `password=${DB_PASS}` is correctly treated as an
    indirection, while `password="${DB_PASS}"` -- the same indirection, in
    the quoting style Gradle and YAML both use -- is reported as a literal
    credential. Found in a real build script, where every `password` line was
    a quoted `${...}` and every one of them was flagged.

    This only ever makes the placeholder test MORE likely to match. A genuine
    quoted secret still fails it (`"hunter2"` -> `hunter2`, not a
    placeholder) and is still reported, so unquoting cannot hide a leak."""
    match = QUOTED_VALUE_RE.match(value.strip())
    return match.group(2).strip() if match else value

# Patterns that are unambiguous enough to flag regardless of the key name
# they're assigned to.
HIGH_CONFIDENCE_PATTERNS = {
    "pem_private_key": re.compile(r"-----BEGIN(?: RSA| EC| OPENSSH)? PRIVATE KEY-----"),
    "aws_access_key_id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}


def _high_confidence_hits(line_no, line):
    return [
        {"line": line_no, "heuristic": name}
        for name, pattern in HIGH_CONFIDENCE_PATTERNS.items()
        if pattern.search(line)
    ]


def _key_name_secret_hit(line_no, line):
    kv = KEY_VALUE_LINE_RE.match(line)
    if not kv:
        return None
    key, value = kv.group(1), kv.group(2)
    if not SECRET_KEY_NAME_RE.search(key):
        return None
    if PLACEHOLDER_VALUE_RE.match(_unquote(value)):
        return None
    return {"line": line_no, "heuristic": f"key-name:{key.lower()}"}


def scan_text_for_secrets(text):
    """Returns a list of {"line": <1-based int>, "heuristic": <name>} dicts
    for lines in `text` that look like they carry a real credential. Never
    returns the matched value itself — callers get a location and a
    heuristic name, nothing that could itself become the leak.
    """
    hits = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        hits.extend(_high_confidence_hits(line_no, line))
        key_hit = _key_name_secret_hit(line_no, line)
        if key_hit is not None:
            hits.append(key_hit)

    return hits
