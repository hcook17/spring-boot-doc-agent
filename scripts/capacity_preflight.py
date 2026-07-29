#!/usr/bin/env python3
"""Thin shim — alias of doc_engine.tools.capacity_preflight.

Run with: python3 scripts/capacity_preflight.py ...
Also: python -m doc_engine.tools.capacity_preflight ...
"""

from __future__ import annotations

import sys

from doc_engine.tools import capacity_preflight as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
