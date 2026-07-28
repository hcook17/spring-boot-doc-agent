"""Application settings (Pydantic Settings — industry-standard config layer)."""

from typing import Any, Dict, List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the doc-engine SDK and CLI."""

    model_config = SettingsConfigDict(
        env_prefix="DOC_ENGINE_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    scanners: List[str] = Field(
        default_factory=lambda: ["filesystem", "ast-grep"],
        description="Ordered scanner names to run.",
    )
    sql_dialect: str = "ansi"
    respect_gitignore: bool = False
    build_command: Optional[str] = None
    db_path: Optional[str] = None
    doc_taxonomy: Optional[List[str]] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


# Backward-compatible alias used by Engine and CLI.
Config = Settings
