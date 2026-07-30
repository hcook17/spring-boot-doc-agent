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


def _namespaces_from_package(package: Optional[str]) -> tuple[str, ...]:
    if package is None or package == "":
        return ()
    parts = tuple(p for p in package.split(".") if p)
    if not parts or any(not p for p in package.split(".")):
        raise SymbolError(f"invalid package: {package!r}")
    for p in parts:
        _validate_java_ident(p, what="package segment")
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


def parse(symbol: str) -> ParsedSymbol:
    """Parse a claim-symbol into structured parts."""
    if not isinstance(symbol, str) or not symbol.startswith(_PREFIX):
        raise SymbolError(f"unparseable symbol: {symbol!r}")
    rest = symbol[len(_PREFIX) :]
    if not rest:
        raise SymbolError(f"unparseable symbol: {symbol!r}")

    kind = "type"
    member: Optional[str] = None
    body = rest

    if body.endswith("()."):
        kind = "method"
        hash_idx = body.rfind("#")
        if hash_idx < 0:
            raise SymbolError(f"unparseable method symbol: {symbol!r}")
        member_part = body[hash_idx + 1 :]
        if not member_part.endswith("()."):
            raise SymbolError(f"unparseable method symbol: {symbol!r}")
        member = member_part[:-3]
        _validate_java_ident(member, what="method name")
        body = body[: hash_idx + 1]
    elif body.endswith(".") and "#" in body:
        # field: …#field.  (type form ends with # alone — not a field)
        hash_idx = body.rfind("#")
        member_part = body[hash_idx + 1 :]
        if member_part.endswith(".") and member_part != ".":
            member = member_part[:-1]
            if "(" in member or ")" in member or not member:
                raise SymbolError(f"unparseable field symbol: {symbol!r}")
            _validate_java_ident(member, what="field name")
            kind = "field"
            body = body[: hash_idx + 1]

    if not body.endswith("#"):
        raise SymbolError(f"type descriptor must end with '#': {symbol!r}")

    # Split namespaces from type chain: ns/ns/Outer#Inner#
    # Types are '#"-separated and body ends with '#'.
    type_body = body
    slash = type_body.rfind("/")
    if slash >= 0:
        ns_part = type_body[:slash]
        type_part = type_body[slash + 1 :]
        namespaces = tuple(ns_part.split("/")) if ns_part else ()
    else:
        namespaces = ()
        type_part = type_body

    if not type_part.endswith("#"):
        raise SymbolError(f"unparseable symbol: {symbol!r}")
    type_names = tuple(t for t in type_part.split("#") if t)
    if not type_names:
        raise SymbolError(f"missing type name: {symbol!r}")
    for n in namespaces:
        _validate_java_ident(n, what="package segment")
    for n in type_names:
        _validate_java_ident(n, what="type name")

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
