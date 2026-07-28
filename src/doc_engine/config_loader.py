"""Backward-compatible re-export of repository config loading."""

from doc_engine.config.loader import find_repo_config, load_repo_config, merge_config

__all__ = ["find_repo_config", "load_repo_config", "merge_config"]
