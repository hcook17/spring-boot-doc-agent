#!/usr/bin/env python3
"""CLI entry for local pipeline runs.

Implementation: doc_engine.pipeline.local_runner

Usage:
    python3 scripts/run_pipeline_local.py /abs/path/to/spring-repo
"""

from __future__ import annotations

from doc_engine.pipeline.local_runner import main

if __name__ == "__main__":
    raise SystemExit(main())
