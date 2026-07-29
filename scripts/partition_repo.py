#!/usr/bin/env python3
"""Thin shim — alias of doc_engine.tools.partition_repo.

Run with: python3 scripts/partition_repo.py ...
Also: python -m doc_engine.tools.partition_repo ...
"""

from __future__ import annotations

import sys

from doc_engine.tools import partition_repo as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
