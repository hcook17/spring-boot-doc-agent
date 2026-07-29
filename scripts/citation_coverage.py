#!/usr/bin/env python3
"""Thin shim — alias of doc_engine.tools.citation_coverage.

Run with: python3 scripts/citation_coverage.py ...
Also: python -m doc_engine.tools.citation_coverage ...
"""

from __future__ import annotations

import sys

from doc_engine.tools import citation_coverage as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
