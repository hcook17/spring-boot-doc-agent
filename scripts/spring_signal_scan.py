#!/usr/bin/env python3
"""Thin shim — alias of doc_engine.tools.spring_signal_scan.

Run with: python3 scripts/spring_signal_scan.py ...
Also: python -m doc_engine.tools.spring_signal_scan ...
"""

from __future__ import annotations

import sys

from doc_engine.tools import spring_signal_scan as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
