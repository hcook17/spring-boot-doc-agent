#!/usr/bin/env python3
"""Thin shim — alias of doc_engine.tools.run_manifest.

Run with: python3 scripts/run_manifest.py ...
Also: python -m doc_engine.tools.run_manifest ...
"""

from __future__ import annotations

import sys

from doc_engine.tools import run_manifest as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
