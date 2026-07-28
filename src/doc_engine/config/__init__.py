"""Configuration package."""

from doc_engine.config.loader import load_repo_config, merge_config
from doc_engine.config.settings import Config, Settings

__all__ = ["Config", "Settings", "load_repo_config", "merge_config"]
