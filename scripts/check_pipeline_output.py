#!/usr/bin/env python3
"""Thin shim — alias of doc_engine.tools.check_pipeline_output.

Run with: python3 scripts/check_pipeline_output.py ...
Also: python -m doc_engine.tools.check_pipeline_output ...
"""

from __future__ import annotations

import sys

from doc_engine.tools import check_pipeline_output as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
