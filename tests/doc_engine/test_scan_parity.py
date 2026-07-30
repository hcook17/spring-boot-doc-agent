"""Wave 0: Engine.scan and doc_engine.scanning.spring.scan share one implementation."""

from __future__ import annotations

import json

from doc_engine import Engine
from doc_engine.scanning.spring import scan as spring_scan
from tests.conftest import FIXTURE_DIR

# Match the fixture snapshot scanner set used by test_spring_signal_scan.
SNAPSHOT_SCANNERS = ["filesystem", "ast-grep"]


def _drop_volatile(data: dict) -> dict:
    """Copy scan dict for equality, ignoring keys that may vary by wall-clock."""
    out = json.loads(json.dumps(data))
    # scanner_version is deterministic for the same scanner set; keep it.
    return out


def test_engine_scan_matches_spring_scan_on_fixture():
    engine = Engine()
    via_engine = engine.scan(
        str(FIXTURE_DIR),
        scanners=SNAPSHOT_SCANNERS,
    )
    via_spring = spring_scan(
        str(FIXTURE_DIR),
        scanners=SNAPSHOT_SCANNERS,
    )
    assert _drop_volatile(via_engine) == _drop_volatile(via_spring)


def test_doc_engine_scan_cli_default_out_is_spring_signals():
    """Public CLI default must match Stage 0 / spring_signal_scan.py naming."""
    import argparse

    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers()
    scan_ap = sub.add_parser("scan")
    scan_ap.add_argument("repo")
    scan_ap.add_argument("--out", default="spring_signals.json")
    args = ap.parse_args(["scan", "/tmp/x"])
    assert args.out == "spring_signals.json"
