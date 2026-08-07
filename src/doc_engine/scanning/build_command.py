"""Validate CodeQL build commands before passing them to subprocess.

CodeQL ``database create --command`` executes the string under instrumentation
(CWE-78/88). Target-repo config is untrusted by default, so this allowlist is
exact-basename only: no ``startswith`` prefixes, and shells are accepted only
when they wrap a known build-tool basename as the next token.
"""

from __future__ import annotations

import re
import shlex
from typing import Optional


class BuildCommandError(ValueError):
    """Raised when a build command string is unsafe or unsupported."""


_SHELL_METACHAR_RE = re.compile(
    r"[;|&`$<>]|&&|\|\||\$\(|\n|\r"
)

_ALLOWED_TOOLS = frozenset({
    "gradlew",
    "gradlew.bat",
    "gradle",
    "gradle.bat",
    "mvnw",
    "mvnw.cmd",
    "mvn",
    "mvn.cmd",
})

_SHELL_WRAPPERS = frozenset({
    "bash",
    "bash.exe",
    "sh",
    "sh.exe",
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
})


def _token_basename(token: str) -> str:
    return token.strip('"').strip("'").replace("\\", "/").rsplit("/", 1)[-1].lower()


def validate_build_command(build_command: Optional[str]) -> str:
    """Reject build commands that embed shell chaining or unknown tools.

    Accepted shapes:
    - ``gradlew|mvn|…`` (exact basename) plus args
    - ``bash|sh|cmd|powershell`` (exact) followed by a token whose basename is
      an allowed build tool (e.g. Git Bash wrapping ``gradlew``)
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

    first = _token_basename(tokens[0])
    if first in _ALLOWED_TOOLS:
        return command

    if first in _SHELL_WRAPPERS:
        if len(tokens) < 2:
            raise BuildCommandError(
                f"shell wrapper {first!r} must be followed by a known build tool "
                f"({', '.join(sorted(_ALLOWED_TOOLS))})"
            )
        second = _token_basename(tokens[1])
        if second not in _ALLOWED_TOOLS:
            raise BuildCommandError(
                f"shell wrapper {first!r} must wrap a known build tool, "
                f"got second token basename {second!r}"
            )
        return command

    raise BuildCommandError(
        f"build command must start with a known build tool "
        f"({', '.join(sorted(_ALLOWED_TOOLS))}), got: {first!r}"
    )
