#!/usr/bin/env python3
"""Thin shim — alias of doc_engine.tools.spring_drift_check.

Run with: python3 scripts/spring_drift_check.py ...
Also: python -m doc_engine.tools.spring_drift_check ...
"""

from __future__ import annotations

import sys

from doc_engine.tools import spring_drift_check as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
