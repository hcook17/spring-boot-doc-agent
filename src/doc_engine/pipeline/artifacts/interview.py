"""Interview-answers artifact DTOs.

No ``from __future__ import annotations`` — field types reference StrEnums from
``vocab`` and must resolve at class-body time for Pydantic.
"""

from pydantic import BaseModel, RootModel

from doc_engine.pipeline.artifacts.vocab import InterviewStatus


class InterviewAnswerEntry(BaseModel):
    id: str
    question: str
    status: InterviewStatus
    answer: str | None = None
    date: str


class InterviewAnswersArtifact(RootModel[list[InterviewAnswerEntry]]):
    """interview_answers.json — human-in-the-loop answers."""
