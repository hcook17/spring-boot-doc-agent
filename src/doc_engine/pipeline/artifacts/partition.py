"""Partition / groups artifact DTOs."""

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class SkippedFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    file: str
    reason: str


class GroupEntry(BaseModel):
    id: int
    files: list[str]
    est_tokens: int


class GroupsArtifact(BaseModel):
    """groups.json — partition_repo.py output."""

    repo_path: str
    max_tokens_per_group: int
    overlap: float
    total_files_considered: int
    total_files_skipped: int
    skipped: list[SkippedFile | dict[str, Any]]
    num_groups: int
    groups: list[GroupEntry]

    @field_validator("groups")
    @classmethod
    def groups_len_matches_num_groups(cls, groups: list[GroupEntry], info) -> list[GroupEntry]:
        num = info.data.get("num_groups")
        if num is not None and len(groups) != num:
            raise ValueError(f"groups length {len(groups)} != num_groups {num}")
        return groups
