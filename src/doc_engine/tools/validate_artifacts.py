"""Validate pipeline JSON artifacts — CLI wrapper around kernel validation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from doc_engine.pipeline.artifacts import ARTIFACT_FILENAMES, ARTIFACT_MODELS
from doc_engine.pipeline.validation import (
    ArtifactValidationError,
    missing_required_artifacts,
    require_gap_probe_artifact,
    require_stage0_siblings,
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
    parser.add_argument(
        "--require",
        metavar="NAMES",
        help=(
            "comma-separated artifact registry keys that must be present under "
            "--all DIR (missing → exit 1). Default --all still skips absences."
        ),
    )
    parser.add_argument("artifact", nargs="?", help="artifact name")
    parser.add_argument("path", nargs="?", help="path to JSON file")
    args = parser.parse_args(argv)

    if args.list:
        for name, filename in sorted(ARTIFACT_FILENAMES.items()):
            print(f"{name}\t{filename}")
        return 0

    if args.require and not args.all:
        parser.error("--require requires --all DIR")

    if args.all:
        directory = Path(args.all)
        if not directory.is_dir():
            print(f"error: not a directory: {directory}", file=sys.stderr)
            return 2
        required: list[str] = []
        if args.require:
            required = [n.strip() for n in args.require.split(",") if n.strip()]
            if not required:
                parser.error("--require needs at least one artifact name")
            try:
                missing = missing_required_artifacts(directory, required)
            except KeyError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            if missing:
                print(
                    f"error: required artifact(s) missing in {directory}: "
                    f"{', '.join(missing)}",
                    file=sys.stderr,
                )
                return 1
        try:
            require_stage0_siblings(directory)
            require_gap_probe_artifact(directory)
            validated = validate_artifacts_in_dir(directory)
        except (ArtifactValidationError, FileNotFoundError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if not validated and not required:
            print(f"error: no known artifact files found in {directory}", file=sys.stderr)
            return 1
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
