#!/usr/bin/env python3
"""Validate pipeline JSON artifacts against documented schemas.

Usage:
    python3 scripts/validate_artifacts.py spring_signals path/to/spring_signals.json
    python3 scripts/validate_artifacts.py --all /path/to/run-directory
    python3 scripts/validate_artifacts.py --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from doc_engine.pipeline.artifacts import ARTIFACT_FILENAMES, ARTIFACT_MODELS  # noqa: E402
from doc_engine.pipeline.validation import (  # noqa: E402
    ArtifactValidationError,
    validate_artifact_file,
    validate_artifacts_in_dir,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--list",
        action="store_true",
        help="list known artifact names and filenames",
    )
    parser.add_argument(
        "--all",
        metavar="DIR",
        help="validate every known artifact file present in DIR",
    )
    parser.add_argument(
        "artifact",
        nargs="?",
        help="artifact name (spring_signals, groups, summaries, interview_answers)",
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="path to the JSON file",
    )
    args = parser.parse_args(argv)

    if args.list:
        for name, filename in sorted(ARTIFACT_FILENAMES.items()):
            print(f"{name}\t{filename}")
        return 0

    if args.all:
        directory = Path(args.all)
        if not directory.is_dir():
            print(f"error: not a directory: {directory}", file=sys.stderr)
            return 2
        try:
            validated = validate_artifacts_in_dir(directory)
        except (ArtifactValidationError, FileNotFoundError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if not validated:
            print(f"warning: no known artifact files found in {directory}", file=sys.stderr)
            return 0
        for artifact, path in validated:
            print(f"OK  {artifact}  {path}")
        return 0

    if not args.artifact or not args.path:
        parser.error("provide ARTIFACT PATH or use --all DIR")

    if args.artifact not in ARTIFACT_MODELS:
        print(
            f"error: unknown artifact {args.artifact!r}; expected one of {sorted(ARTIFACT_MODELS)}",
            file=sys.stderr,
        )
        return 2

    try:
        validate_artifact_file(args.artifact, Path(args.path))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ArtifactValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"OK  {args.artifact}  {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
