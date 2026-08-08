"""SCIP-inspired claim-symbol grammar for facts SoR identity (L3).

Normative forms (placeholders for package manager name/version until real
module coordinates exist)::

    doc-engine spring . <ns>/(<ns>/)*<Type>#
    doc-engine spring . <ns>/(<ns>/)*<Type>#<Inner>#
    doc-engine spring . <ns>/(<ns>/)*<Type>#<field>.
    doc-engine spring . <ns>/(<ns>/)*<Type>#<method>().

Missing Java ``package`` → no namespace segments (unqualified type form).
Do not invent packages from file paths.

Sole writer API for machine identity strings — do not concatenate subjects
in ``facts.py``. Member formatters are reserved (tested) until member facts exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

SYMBOL_GRAMMAR_VERSION = 1

SCHEME = "doc-engine"
MANAGER = "spring"
# Single placeholder token for package name/version until real module coordinates exist.
PACKAGE_COORD_PLACEHOLDER = "."

_PREFIX = f"{SCHEME} {MANAGER} {PACKAGE_COORD_PLACEHOLDER} "


class SymbolError(ValueError):
    """Illegal or unparseable claim-symbol token."""


@dataclass(frozen=True)
class ParsedSymbol:
    kind: str  # "type" | "field" | "method"
    namespaces: tuple[str, ...]
    type_names: tuple[str, ...]  # outer … inner
    member: Optional[str] = None

    @property
    def type_name(self) -> str:
        return self.type_names[-1]

    @property
    def fqcn(self) -> str:
        types = ".".join(self.type_names)
        if self.namespaces:
            return ".".join(self.namespaces) + "." + types
        return types


def _validate_java_ident(name: str, *, what: str) -> str:
    """Accept simple Java-like identifiers (letter/underscore start; alnum/_ body)."""
    if not name or not (name[0].isalpha() or name[0] == "_"):
        raise SymbolError(f"invalid {what}: {name!r}")
    if not all(c.isalnum() or c == "_" for c in name):
        raise SymbolError(f"invalid {what}: {name!r}")
    return name


def _package_has_empty_segment(package: str) -> bool:
    """True when ``package`` contains a leading/trailing/double-dot empty segment."""
    return any(not part for part in package.split("."))


def _split_package_segments(package: str) -> tuple[str, ...]:
    """Split a non-empty package string into validated-nonempty segments."""
    if _package_has_empty_segment(package):
        raise SymbolError(f"invalid package: {package!r}")
    parts = tuple(p for p in package.split(".") if p)
    if not parts:
        raise SymbolError(f"invalid package: {package!r}")
    return parts


def _namespaces_from_package(package: Optional[str]) -> tuple[str, ...]:
    if package is None or package == "":
        return ()
    parts = _split_package_segments(package)
    for part in parts:
        _validate_java_ident(part, what="package segment")
    return parts


def _type_chain(type_name: str, inner: Sequence[str]) -> tuple[str, ...]:
    names = (type_name, *inner)
    for n in names:
        _validate_java_ident(n, what="type name")
    return names


def _path_prefix(namespaces: Sequence[str], type_names: Sequence[str]) -> str:
    ns = "/".join(namespaces)
    # Type chain: Outer#Inner#  (SCIP-like nested type descriptors)
    types = "#".join(type_names) + "#"
    if ns:
        return f"{ns}/{types}"
    return types


def format_type(
    package: Optional[str],
    type_name: str,
    *,
    inner: Sequence[str] = (),
) -> str:
    """Format a type-level claim-symbol."""
    namespaces = _namespaces_from_package(package)
    type_names = _type_chain(type_name, inner)
    return _PREFIX + _path_prefix(namespaces, type_names)


def format_field(
    package: Optional[str],
    type_name: str,
    field: str,
    *,
    inner: Sequence[str] = (),
) -> str:
    """Format a field-level claim-symbol (reserved; not emitted in L3 type PR)."""
    _validate_java_ident(field, what="field name")
    base = format_type(package, type_name, inner=inner)
    # type form ends with '#'; append field.
    return f"{base}{field}."


def format_method(
    package: Optional[str],
    type_name: str,
    method: str,
    *,
    inner: Sequence[str] = (),
) -> str:
    """Format a method-level claim-symbol (reserved; not emitted in L3 type PR)."""
    _validate_java_ident(method, what="method name")
    base = format_type(package, type_name, inner=inner)
    return f"{base}{method}()."


def _strip_method_member(body: str, symbol: str) -> tuple[str, str]:
    """Peel a trailing ``Method().`` member; return ``(member, type_body)``."""
    hash_idx = body.rfind("#")
    if hash_idx < 0:
        raise SymbolError(f"unparseable method symbol: {symbol!r}")
    member_part = body[hash_idx + 1 :]
    if not member_part.endswith("()."):
        raise SymbolError(f"unparseable method symbol: {symbol!r}")
    member = member_part[:-3]
    _validate_java_ident(member, what="method name")
    return member, body[: hash_idx + 1]


def _strip_field_member(body: str, symbol: str) -> tuple[Optional[str], str]:
    """Peel a trailing ``field.`` member when present; else leave body unchanged."""
    hash_idx = body.rfind("#")
    member_part = body[hash_idx + 1 :]
    if not (member_part.endswith(".") and member_part != "."):
        return None, body
    member = member_part[:-1]
    if "(" in member or ")" in member or not member:
        raise SymbolError(f"unparseable field symbol: {symbol!r}")
    _validate_java_ident(member, what="field name")
    return member, body[: hash_idx + 1]


def _split_member_suffix(body: str, symbol: str) -> tuple[str, Optional[str], str]:
    """Classify and strip method/field suffixes from a descriptor body."""
    if body.endswith("()."):
        member, type_body = _strip_method_member(body, symbol)
        return "method", member, type_body
    if body.endswith(".") and "#" in body:
        member, type_body = _strip_field_member(body, symbol)
        if member is not None:
            return "field", member, type_body
    return "type", None, body


def _split_ns_and_type_part(type_body: str) -> tuple[tuple[str, ...], str]:
    """Split ``ns/ns/Outer#Inner#`` into namespaces and the type-chain part."""
    slash = type_body.rfind("/")
    if slash < 0:
        return (), type_body
    ns_part = type_body[:slash]
    type_part = type_body[slash + 1 :]
    namespaces = tuple(ns_part.split("/")) if ns_part else ()
    return namespaces, type_part


def _parse_type_names(type_part: str, symbol: str) -> tuple[str, ...]:
    if not type_part.endswith("#"):
        raise SymbolError(f"unparseable symbol: {symbol!r}")
    type_names = tuple(t for t in type_part.split("#") if t)
    if not type_names:
        raise SymbolError(f"missing type name: {symbol!r}")
    return type_names


def _validate_parsed_idents(
    namespaces: tuple[str, ...],
    type_names: tuple[str, ...],
) -> None:
    for name in namespaces:
        _validate_java_ident(name, what="package segment")
    for name in type_names:
        _validate_java_ident(name, what="type name")


def parse(symbol: str) -> ParsedSymbol:
    """Parse a claim-symbol into structured parts."""
    if not isinstance(symbol, str) or not symbol.startswith(_PREFIX):
        raise SymbolError(f"unparseable symbol: {symbol!r}")
    rest = symbol[len(_PREFIX) :]
    if not rest:
        raise SymbolError(f"unparseable symbol: {symbol!r}")

    kind, member, type_body = _split_member_suffix(rest, symbol)
    if not type_body.endswith("#"):
        raise SymbolError(f"type descriptor must end with '#': {symbol!r}")

    namespaces, type_part = _split_ns_and_type_part(type_body)
    type_names = _parse_type_names(type_part, symbol)
    _validate_parsed_idents(namespaces, type_names)

    return ParsedSymbol(
        kind=kind,
        namespaces=namespaces,
        type_names=type_names,
        member=member,
    )


def display(symbol: str) -> str:
    """Human display form: ``User``, ``Order.Line``, ``User.email``, ``User.getOrders()``."""
    parsed = parse(symbol)
    type_disp = ".".join(parsed.type_names)
    if parsed.kind == "type":
        return type_disp
    if parsed.kind == "field":
        return f"{type_disp}.{parsed.member}"
    if parsed.kind == "method":
        return f"{type_disp}.{parsed.member}()"
    raise SymbolError(f"unknown kind: {parsed.kind!r}")


def fqcn_of(package: Optional[str], type_name: str, *, inner: Sequence[str] = ()) -> str:
    """Java-style FQCN for qualifiers (display/join aid, not the machine subject)."""
    type_names = _type_chain(type_name, inner)
    types = ".".join(type_names)
    if package:
        _namespaces_from_package(package)  # validate
        return f"{package}.{types}"
    return types
