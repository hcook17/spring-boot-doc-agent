"""
_config_keys.py — mechanical config-key-path extraction, no YAML dependency.

WHY THIS EXISTS
Deliberately not a YAML parser dependency (this project has no non-stdlib
hard dependency anywhere — PyYAML would be the first). Spring Boot config
files are simple enough (nested mappings, scalar leaf values, no anchors/
multi-doc/tags in practice) that a mechanical indentation-stack walk gets
the thing that actually matters here — the *set of dotted key paths* a
file defines — without needing a real parser. Values are never inspected
beyond "is this line a leaf (has an inline value) or a group header
(nothing after the colon, a nested mapping follows)".

WHAT THIS IS FOR
spring_signal_scan.py records the key set for every configuration/
deployment file as `config_key_sets`. spring_drift_check.py compares that
snapshot to a fresh extraction on re-run and distinguishes two very
different kinds of change to the exact same file:

  - key set changed (something added/removed) — an expected, structural
    evolution of the config's own shape ("config_structure_changed").
  - key set identical, but the file's content hash changed anyway — the
    only way that happens is a *value* changed under an unchanged key.
    In a setup where these files are checked-in placeholders/dummies and
    real values are injected by an external service at deploy time (the
    stated assumption this check is built for), that's the anomalous
    case: a value changing with no structural reason to touch the file at
    all is worth a human look, not a routine one
    ("config_values_only_changed_review_needed").

WHAT THIS DOES NOT DO
No list-item traversal (`- foo` lines are skipped, not walked into) and no
handling of YAML flow-style mappings (`{a: 1, b: 2}` on one line) — both
are rare in Spring Boot config in practice, and this is a heuristic key-
path extractor, not a spec-complete YAML parser. A key inside either shape
just won't appear in the returned set; that's a stated, narrow gap, not
silent miscounting of keys that were actually extracted.
"""

import re

_YAML_KEY_LINE_RE = re.compile(r'^(?P<indent>\s*)(?P<key>[\w.\-]+|"[^"]*"|\'[^\']*\')\s*:\s*(?P<value>.*)$')
_PROPERTIES_KEY_LINE_RE = re.compile(r"^\s*([\w.\-]+)\s*[:=]\s*.*$")


def _strip_quotes(key):
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
        return key[1:-1]
    return key


def _is_skippable_yaml_line(raw_line):
    if not raw_line.strip() or raw_line.strip().startswith("#"):
        return True
    return raw_line.lstrip().startswith("-")  # list items: out of scope


def _pop_yaml_stack(stack, indent):
    while stack and stack[-1][0] >= indent:
        stack.pop()


def _record_yaml_key(keys, stack, indent, key, value):
    path = ".".join(name for _, name in stack + [(indent, key)])
    if value and not value.startswith("#"):
        keys.append(path)
        return
    stack.append((indent, key))


def _extract_yaml_keys(text):
    """Indentation-stack walk: a line's dotted path is the stack of every
    ancestor group key joined with ".". Only leaf lines (a key with a
    non-empty inline value) are returned — a bare group header contributes
    to the path of its children but isn't itself a configurable property.
    """
    keys = []
    stack = []  # list of (indent_width, key_name)

    for raw_line in text.splitlines():
        if _is_skippable_yaml_line(raw_line):
            continue
        match = _YAML_KEY_LINE_RE.match(raw_line)
        if not match:
            continue
        indent = len(match.group("indent"))
        key = _strip_quotes(match.group("key"))
        value = match.group("value").strip()
        _pop_yaml_stack(stack, indent)
        _record_yaml_key(keys, stack, indent, key, value)

    return keys


def _is_skippable_properties_line(stripped):
    return not stripped or stripped.startswith("#") or stripped.startswith("!")


def _extract_properties_keys(text):
    keys = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if _is_skippable_properties_line(stripped):
            continue
        match = _PROPERTIES_KEY_LINE_RE.match(raw_line)
        if match:
            keys.append(match.group(1))
    return keys


def extract_config_keys(text, filename):
    """Returns a sorted, deduplicated list of dotted config key paths found
    in `text`. `filename` decides the dialect (.properties vs YAML); any
    other extension (e.g. a Dockerfile) returns an empty list — this is
    scoped to key-path-shaped config formats, not every deployment file
    spring_signal_scan.py's "deployment" bucket happens to include.
    """
    lower = filename.lower()
    if lower.endswith(".properties"):
        keys = _extract_properties_keys(text)
    elif lower.endswith(".yml") or lower.endswith(".yaml"):
        keys = _extract_yaml_keys(text)
    else:
        keys = []
    return sorted(set(keys))
