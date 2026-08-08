"""Small stdlib shims for the declared ``requires-python`` floor (>=3.10)."""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:  # pragma: no cover -- exercised on the 3.10 CI matrix cell
    from enum import Enum

    class StrEnum(str, Enum):
        """Minimal ``enum.StrEnum`` backport for Python 3.10."""

        def __str__(self) -> str:
            return str(self.value)


__all__ = ["StrEnum"]
