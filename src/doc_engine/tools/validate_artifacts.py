"""Validate pipeline JSON artifacts — CLI wrapper around kernel validation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from doc_engine.pipeline.artifacts import ARTIFACT_FILENAMES, ARTIFACT_MODELS
from doc_engine.pipeline.validation import (
    ArtifactValidationError,
    validate_artifact_file,
    validate_artifacts_in_dir,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate pipeline JSON artifacts against documented schemas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list", action="store_true", help="list known artifact names")
    parser.add_argument("--all", metavar="DIR", help="validate every known artifact in DIR")
    parser.add_argument("artifact", nargs="?", help="artifact name")
    parser.add_argument("path", nargs="?", help="path to JSON file")
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
            f"error: unknown artifact {args.artifact!r}; "
            f"expected one of {sorted(ARTIFACT_MODELS)}",
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
