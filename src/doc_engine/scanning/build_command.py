"""Validate CodeQL build commands before passing them to subprocess.

CodeQL ``database create --command`` executes the string under instrumentation
inside ``--source-root`` (CWE-78/88). An allowlist of tool *names* cannot make
an untrusted tree safe to build — that requires refusing CodeQL build mode
(see ``RepoConfigTrust`` / ``--allow-codeql-build``). This module only removes
foot-guns: exact basenames, bash/sh wrappers that actually wrap a tool, and
known arbitrary-code flags (``-I``, ``--init-script``, ``-s``, …).
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
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

# Only shapes with a real use case (Git Bash → gradlew). cmd/powershell
# second-token normalization turns ``/c`` into ``c`` and breaks legitimate
# wrappers while still not making untrusted builds safe.
_SHELL_WRAPPERS = frozenset({
    "bash",
    "bash.exe",
    "sh",
    "sh.exe",
})

# Flags that load attacker-controlled scripts/settings without shell metacharacters.
_FORBIDDEN_FLAGS = frozenset({
    "-I",
    "--init-script",
    "-s",
    "--settings",
    "--project-cache-dir",
    "--gradle-user-home",
    "--system-properties-file",
})


def _token_basename(token: str) -> str:
    return token.strip('"').strip("'").replace("\\", "/").rsplit("/", 1)[-1].lower()


def _flag_name(token: str) -> str:
    stripped = token.strip('"').strip("'")
    if stripped.startswith("--") and "=" in stripped:
        return stripped.split("=", 1)[0]
    return stripped


def _reject_dangerous_flags(tokens: list[str]) -> None:
    for token in tokens[1:]:
        name = _flag_name(token)
        if name in _FORBIDDEN_FLAGS:
            raise BuildCommandError(
                f"build command flag {name!r} is not allowed "
                f"(loads external scripts/settings under CodeQL --command)"
            )


def _strip_outer_quotes(token: str) -> str:
    stripped = token.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "'\"":
        return stripped[1:-1]
    return stripped


def _canonicalize_tokens(tokens: list[str]) -> str:
    """Rejoin validated tokens so the return value is derived from the parse."""
    cleaned = [_strip_outer_quotes(t) for t in tokens]
    if sys.platform == "win32":
        return subprocess.list2cmdline(cleaned)
    return shlex.join(cleaned)


def _require_nonempty_command(build_command: Optional[str]) -> str:
    if build_command is None or not str(build_command).strip():
        raise BuildCommandError("build command is empty")
    return str(build_command).strip()


def _reject_shell_metacharacters(command: str) -> None:
    if _SHELL_METACHAR_RE.search(command):
        raise BuildCommandError(
            "build command contains disallowed shell metacharacters "
            "(chaining, redirection, or substitution). "
            "Pass a single build invocation only."
        )


def _accept_direct_tool(tokens: list[str], first: str) -> Optional[str]:
    if first not in _ALLOWED_TOOLS:
        return None
    _reject_dangerous_flags(tokens)
    return _canonicalize_tokens(tokens)


def _accept_shell_wrapper(tokens: list[str], first: str) -> Optional[str]:
    if first not in _SHELL_WRAPPERS:
        return None
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
    _reject_dangerous_flags(tokens)
    return _canonicalize_tokens(tokens)


def validate_build_command(build_command: Optional[str]) -> str:
    """Reject shell chaining, unknown tools, and known arbitrary-code flags.

    Accepted shapes:
    - exact build-tool basename plus args
    - ``bash``/``sh`` followed by a token whose basename is an allowed tool

    Returns a canonical rejoined form of the validated tokens (not a blind
    echo of the input), so callers pass only the allowlisted parse forward.
    """
    command = _require_nonempty_command(build_command)
    _reject_shell_metacharacters(command)
    tokens = shlex.split(command, posix=False)
    if not tokens:
        raise BuildCommandError("build command is empty")
    first = _token_basename(tokens[0])
    accepted = _accept_direct_tool(tokens, first) or _accept_shell_wrapper(tokens, first)
    if accepted is not None:
        return accepted
    raise BuildCommandError(
        f"build command must start with a known build tool "
        f"({', '.join(sorted(_ALLOWED_TOOLS))}), got: {first!r}"
    )
