#!/usr/bin/env python3
"""Thin shim — implementation in doc_engine.pipeline.local_runner.

Usage:
    python3 scripts/run_pipeline_local.py /abs/path/to/spring-repo
"""

from __future__ import annotations

import sys

import doc_engine.pipeline.local_runner as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
