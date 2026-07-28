#!/usr/bin/env python3
"""Exit 0 only when certification.json exists and reports certified: true."""

from __future__ import annotations

from doc_engine.tools.certification import main

if __name__ == "__main__":
    raise SystemExit(main())
