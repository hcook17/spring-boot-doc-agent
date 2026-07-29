#!/usr/bin/env python3
"""CLI entry for pipeline artifact shape validators.

Implementation: doc_engine.tools.pipeline_validators

Usage:
    python3 scripts/pipeline_validators.py <run-directory> --target-repo <repo>
"""

from __future__ import annotations

from doc_engine.tools.pipeline_validators import main

if __name__ == "__main__":
    raise SystemExit(main())
