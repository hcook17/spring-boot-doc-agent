#!/usr/bin/env python3
"""Validate pipeline JSON artifacts against documented schemas.

Implementation: doc_engine.tools.validate_artifacts

Usage:
    python3 scripts/validate_artifacts.py spring_signals <path>
"""

from __future__ import annotations

from doc_engine.tools.validate_artifacts import main

if __name__ == "__main__":
    raise SystemExit(main())
