"""Validate CodeQL build commands before passing them to subprocess."""

import re
import shlex
from typing import Optional


class BuildCommandError(ValueError):
    """Raised when a build command string is unsafe or unsupported."""


_SHELL_METACHAR_RE = re.compile(
    r"[;|&`$<>]|&&|\|\||\$\(|\n|\r"
)

_ALLOWED_PREFIXES = (
    "gradlew",
    "gradle",
    "mvnw",
    "mvn",
    "bash",
    "sh",
    "cmd",
    "powershell",
)


def validate_build_command(build_command: Optional[str]) -> str:
    """Reject build commands that embed shell chaining or redirection.

    CodeQL passes the command string to ``codeql database create --command``.
    This validator is intentionally conservative for untrusted inputs: only
    simple single-invocation build commands are accepted.
    """
    if build_command is None or not str(build_command).strip():
        raise BuildCommandError("build command is empty")

    command = str(build_command).strip()
    if _SHELL_METACHAR_RE.search(command):
        raise BuildCommandError(
            "build command contains disallowed shell metacharacters "
            "(chaining, redirection, or substitution). "
            "Pass a single build invocation only."
        )

    tokens = shlex.split(command, posix=False)
    if not tokens:
        raise BuildCommandError("build command is empty")
    first_token = tokens[0].strip('"').strip("'").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if not any(first_token == prefix or first_token.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
        raise BuildCommandError(
            f"build command must start with a known build tool "
            f"({', '.join(_ALLOWED_PREFIXES)}), got: {first_token!r}"
        )

    return command
