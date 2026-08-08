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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate pipeline JSON artifacts against documented schemas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list", action="store_true", help="list known artifact names")
    parser.add_argument("--all", metavar="DIR", help="validate every known artifact in DIR")
    parser.add_argument(
        "--envelope",
        nargs=2,
        metavar=("KIND", "PATH"),
        help="validate query_result|context_packet envelope JSON at PATH",
    )
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
    return parser


def _handle_envelope(kind: str, path_s: str) -> int:
    from doc_engine.query.load import QueryError, load_json
    from doc_engine.query.schema_check import validate_envelope

    try:
        data = load_json(path_s)
        if not isinstance(data, dict):
            print("error: envelope must be a JSON object", file=sys.stderr)
            return 1
        validate_envelope(kind, data)
    except QueryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"ok: {kind} {path_s}")
    return 0


def _handle_list() -> int:
    for name, filename in sorted(ARTIFACT_FILENAMES.items()):
        print(f"{name}\t{filename}")
    return 0


def _parse_required_names(raw: str | None, parser: argparse.ArgumentParser) -> list[str]:
    if not raw:
        return []
    required = [name.strip() for name in raw.split(",") if name.strip()]
    if not required:
        parser.error("--require needs at least one artifact name")
    return required


def _check_required_present(directory: Path, required: list[str]) -> int | None:
    """Return an exit code on failure, or None when all required artifacts exist."""
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
    return None


def _handle_all(directory: Path, required: list[str]) -> int:
    if not directory.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return 2
    if required:
        required_exit = _check_required_present(directory, required)
        if required_exit is not None:
            return required_exit
    return _validate_directory_contents(directory, required)


def _validate_directory_contents(directory: Path, required: list[str]) -> int:
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


def _validate_single_file(artifact: str, path: str) -> int:
    try:
        validate_artifact_file(artifact, Path(path))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ArtifactValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"OK  {artifact}  {path}")
    return 0


def _handle_single(artifact: str, path: str) -> int:
    if artifact not in ARTIFACT_MODELS:
        print(
            f"error: unknown artifact {artifact!r}; "
            f"expected one of {sorted(ARTIFACT_MODELS)}",
            file=sys.stderr,
        )
        return 2
    return _validate_single_file(artifact, path)


def _dispatch_flag_modes(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int | None:
    """Handle --envelope / --list / --all; return None to fall through to positional."""
    if args.envelope:
        kind, path_s = args.envelope
        return _handle_envelope(kind, path_s)
    if args.list:
        return _handle_list()
    if args.require and not args.all:
        parser.error("--require requires --all DIR")
    if args.all:
        required = _parse_required_names(args.require, parser)
        return _handle_all(Path(args.all), required)
    return None


def _dispatch_cli(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    flag_exit = _dispatch_flag_modes(parser, args)
    if flag_exit is not None:
        return flag_exit
    if not args.artifact or not args.path:
        parser.error("provide ARTIFACT PATH or use --all DIR")
    return _handle_single(args.artifact, args.path)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return _dispatch_cli(parser, args)
