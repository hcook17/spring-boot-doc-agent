#!/usr/bin/env python3
"""Backward-compatible runner — implementation in tests/test_set_delta."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for entry in (ROOT, ROOT / "src"):
    path = str(entry)
    if path not in sys.path:
        sys.path.insert(0, path)

import pytest

if __name__ == "__main__":
    module = Path(__file__).resolve().stem
    args = ["tests/test_set_delta.py"]
    if len(sys.argv) > 1:
        args.extend(sys.argv[1:])
    sys.exit(pytest.main(args))
