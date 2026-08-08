"""Wire vocabulary (StrEnums) for inter-stage artifact DTOs."""

from doc_engine._compat import StrEnum


class InterviewStatus(StrEnum):
    ANSWERED = "answered"
    SKIPPED = "skipped"


class ReviewLens(StrEnum):
    DDIA = "ddia"
    TESTING = "testing"


class ReviewSeverity(StrEnum):
    INFORMATIONAL = "informational"
    WORTH_FLAGGING = "worth-flagging"


class ResearchTiers(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class ResearchVerdict(StrEnum):
    CONFIRMED = "CONFIRMED"
    PLAUSIBLE = "PLAUSIBLE"
    REFUTED = "REFUTED"
    UNRESOLVED = "UNRESOLVED"
