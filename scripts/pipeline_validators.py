#!/usr/bin/env python3
"""Thin shim — implementation in doc_engine.tools.pipeline_validators.

Usage:
    python3 scripts/pipeline_validators.py <run-directory> --target-repo <repo>
"""

from __future__ import annotations

import sys

import doc_engine.tools.pipeline_validators as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
