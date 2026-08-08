"""Unit coverage for dependents edge-path and filter helpers."""

from __future__ import annotations

from doc_engine.query.handlers import dependents as dep


def test_passes_target_filters_self_and_type() -> None:
    assert dep._passes_target_filters("a", "a", "com.X", None, None) is False
    assert dep._passes_target_filters(
        "src.java", "dst.java", "com.example.Foo", want_file="other.java", want_type=None,
    ) is False
    assert dep._passes_target_filters(
        "src.java", "dst.java", "com.example.Foo", want_file=None, want_type="Bar",
    ) is False
    assert dep._passes_target_filters(
        "src.java", "dst.java", "com.example.Foo", want_file=None, want_type="Foo",
    ) is True


def test_from_edges_group_lookup_and_filters() -> None:
    edges = {
        "groups": {
            "1": {
                "outbound": [{"from": "a.java", "to": "b.java", "via": "x"}],
                "inbound": [{"from": "c.java", "to": "a.java", "via": "y"}],
            }
        }
    }
    all_arcs = dep.query_dependents({}, edges=edges, group_id=1)
    assert {arc["direction"] for arc in all_arcs} == {"outbound", "inbound"}

    only_a = dep.query_dependents({}, edges=edges, group_id="1", target_file="a.java")
    assert only_a
    assert all(
        arc["from"].replace("\\", "/") == "a.java"
        or arc["to"].replace("\\", "/") == "a.java"
        for arc in only_a
    )

    assert dep.query_dependents({}, edges=edges, group_id=99) == []
    assert dep.query_dependents({}, edges={"per_group": {}}, group_id=1) == []


def test_from_references_non_list() -> None:
    assert dep.query_dependents({"evidence": {"references": {"nope": True}}}) == []


def test_arc_direction() -> None:
    assert dep._arc_direction("a.java", "b.java", "a.java") == "outbound"
    assert dep._arc_direction("a.java", "b.java", "b.java") == "inbound"
    assert dep._arc_direction("a.java", "b.java", None) == "outbound"
