"""Claim-symbol grammar contracts (L3).

Each test names a deviation it must catch. Golden full-string equality only
for examples frozen in claim-symbol-grammar-2026-07-30.md §3.
"""

from __future__ import annotations

import pytest

from doc_engine.scanning.symbol import (
    SYMBOL_GRAMMAR_VERSION,
    SymbolError,
    display,
    format_field,
    format_method,
    format_type,
    fqcn_of,
    parse,
)

# Frozen golden from grammar memo §3 — only full-string anchors allowed here.
GOLDEN_BILLING_USER = "doc-engine spring . com/acme/billing/User#"
GOLDEN_AUTH_USER = "doc-engine spring . com/acme/auth/User#"
GOLDEN_UNQUALIFIED_ORDER = "doc-engine spring . Order#"
GOLDEN_INNER = "doc-engine spring . com/acme/Order#Line#"
GOLDEN_FIELD = "doc-engine spring . com/acme/billing/User#email."
GOLDEN_METHOD = "doc-engine spring . com/acme/billing/User#getOrders()."


def test_grammar_version_pinned() -> None:
    """Deviation: shipping without a grammar version constant."""
    assert SYMBOL_GRAMMAR_VERSION == 1


def test_golden_billing_user_matches_memo() -> None:
    """Deviation: type spelling drifts from normative grammar memo §3."""
    assert format_type("com.acme.billing", "User") == GOLDEN_BILLING_USER
    parsed = parse(GOLDEN_BILLING_USER)
    assert parsed.kind == "type"
    assert parsed.namespaces == ("com", "acme", "billing")
    assert parsed.type_names == ("User",)
    assert display(GOLDEN_BILLING_USER) == "User"


def test_collision_packages_yield_unequal_subjects() -> None:
    """Deviation: two packages share one subject for the same simple name."""
    a = format_type("com.acme.billing", "User")
    b = format_type("com.acme.auth", "User")
    assert a == GOLDEN_BILLING_USER
    assert b == GOLDEN_AUTH_USER
    assert a != b
    assert display(a) == display(b) == "User"


def test_missing_package_is_unqualified_not_path_invented() -> None:
    """Deviation: inventing namespaces when package is absent."""
    assert format_type(None, "Order") == GOLDEN_UNQUALIFIED_ORDER
    assert format_type("", "Order") == GOLDEN_UNQUALIFIED_ORDER
    assert parse(GOLDEN_UNQUALIFIED_ORDER).namespaces == ()


def test_inner_type_nested_hash_not_dollar() -> None:
    """Deviation: Java $ binary names leak into symbols, or inner chain breaks."""
    sym = format_type("com.acme", "Order", inner=("Line",))
    assert sym == GOLDEN_INNER
    assert "$" not in sym
    parsed = parse(sym)
    assert parsed.type_names == ("Order", "Line")
    assert display(sym) == "Order.Line"
    assert fqcn_of("com.acme", "Order", inner=("Line",)) == "com.acme.Order.Line"


def test_reserved_field_and_method_round_trip() -> None:
    """Deviation: reserved member forms break before any member fact exists."""
    field = format_field("com.acme.billing", "User", "email")
    method = format_method("com.acme.billing", "User", "getOrders")
    assert field == GOLDEN_FIELD
    assert method == GOLDEN_METHOD
    assert parse(field).kind == "field" and parse(field).member == "email"
    assert parse(method).kind == "method" and parse(method).member == "getOrders"
    assert display(field) == "User.email"
    assert display(method) == "User.getOrders()"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "User",
        "com.acme.User",
        "doc-engine spring . ",
        "doc-engine spring . com/acme/User",
        "doc-engine spring . com/acme/User#email",
        "other spring . com/acme/User#",
    ],
)
def test_parse_rejects_illegal_identity_tokens(bad: str) -> None:
    """Deviation: bare names / FQCNs / malformed symbols accepted as identity."""
    with pytest.raises(SymbolError):
        parse(bad)


def test_format_rejects_non_java_idents() -> None:
    """Deviation: hyphens or junk segments accepted into symbols."""
    with pytest.raises(SymbolError):
        format_type("com.acme", "User-Name")
    with pytest.raises(SymbolError):
        format_field("com.acme", "User", "bad-field")
