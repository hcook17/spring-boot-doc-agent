#!/usr/bin/env python3
"""Thin shim — alias of doc_engine.tools.build_cross_group_edges.

Run with: python3 scripts/build_cross_group_edges.py ...
Also: python -m doc_engine.tools.build_cross_group_edges ...
"""

from __future__ import annotations

import sys

from doc_engine.tools import build_cross_group_edges as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
