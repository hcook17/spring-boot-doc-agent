"""Package extraction contracts for L3 identity (source package, not path)."""

from __future__ import annotations

from doc_engine.scanning.java_extract import extract_entity, extract_java_package


def test_package_comes_from_declaration_not_file_path() -> None:
    """Deviation: inventing package from path `pkg_fake/` when declaration differs."""
    class_snip = "@Entity\n@Table(name = \"users\")\npublic class User {}"
    header = "package com.example.real;\n\n"
    assert extract_java_package(class_snip) is None
    name, entry = extract_entity("pkg_fake/User.java", class_snip, package_source=header)
    assert name == "User"
    assert entry["package"] == "com.example.real"
    assert entry["fqcn"] == "com.example.real.User"
    assert entry["file"] == "pkg_fake/User.java"


def test_missing_package_omits_package_key_keeps_simple_fqcn() -> None:
    """Deviation: fabricating a package when declaration is absent."""
    text = "@Entity\npublic class Order {}"
    name, entry = extract_entity("Order.java", text)
    assert name == "Order"
    assert "package" not in entry
    assert entry["fqcn"] == "Order"
