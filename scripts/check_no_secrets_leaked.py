#!/usr/bin/env python3
"""Thin shim — alias of doc_engine.tools.check_no_secrets_leaked.

Run with: python3 scripts/check_no_secrets_leaked.py ...
Also: python -m doc_engine.tools.check_no_secrets_leaked ...
"""

from __future__ import annotations

import sys

from doc_engine.tools import check_no_secrets_leaked as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
