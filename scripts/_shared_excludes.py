"""Re-export shared exclude rules from doc_engine.core (single source of truth)."""

import _src_bootstrap  # noqa: F401

from doc_engine.core.excludes import DEFAULT_EXCLUDED_DIRS, load_gitignore_spec

__all__ = ["DEFAULT_EXCLUDED_DIRS", "load_gitignore_spec"]
