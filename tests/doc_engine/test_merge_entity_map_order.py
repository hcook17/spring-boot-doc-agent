"""Evidence-before-entity_map merge order must bite when no backend map exists."""

from doc_engine.scanning._merge_signals import merge


def test_entity_map_derived_from_merged_evidence_not_empty_default():
    partials = [
        {
            "evidence": {
                "persistence": [
                    {
                        "rule_id": "persistence__entity",
                        "class_name": "Order",
                        "file": "a/Order.java",
                        "table": "orders",
                        "table_name_source": "explicit",
                        "match": "@Entity",
                        "fqcn": "com.example.Order",
                        "line": 1,
                    }
                ]
            }
        }
    ]
    out = merge(partials, repo_path="/repo", scanner_version="t", scanner_names=["fs"])
    assert "Order" in out["entity_table_map"]
    assert out["entity_table_map"]["Order"]["table"] == "orders"
    assert out["entity_table_map"]["Order"]["file"] == "a/Order.java"


def test_explicit_maps_merged_via_helper_and_contested():
    partials = [
        {
            "entity_table_map": {
                "Order": {
                    "file": "a/Order.java",
                    "table": "orders",
                    "table_name_source": "explicit",
                }
            },
            "evidence": {},
        },
        {
            "entity_table_map": {
                "Order": {
                    "file": "b/Order.java",
                    "table": "order_tbl",
                    "table_name_source": "explicit",
                }
            },
            "evidence": {},
        },
    ]
    out = merge(partials, repo_path="/repo", scanner_version="t")
    assert out["entity_table_map"]["Order"]["status"] == "contested"
    assert len(out["entity_table_map"]["Order"]["candidates"]) >= 2
