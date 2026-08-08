"""CLI entry point for the doc-engine package."""

import argparse
import json
import sys
from typing import Any, Dict

from doc_engine import Engine
from doc_engine.config import Config, load_repo_config, merge_config, sanitize_repo_settings, trust_from_flag
from doc_engine.pipeline.local_run import add_run_arguments, run_pipeline


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _scan_config(repo: str, args: argparse.Namespace) -> Config:
    trust = trust_from_flag(bool(getattr(args, "trust_repo_config", False)))
    base = sanitize_repo_settings(load_repo_config(repo) or Config(), trust) or Config()
    overrides: Dict[str, Any] = {}
    if args.scanners:
        overrides["scanners"] = [s.strip() for s in args.scanners.split(",") if s.strip()]
    if args.sql_dialect != "ansi":
        overrides["sql_dialect"] = args.sql_dialect
    if args.respect_gitignore:
        overrides["respect_gitignore"] = True
    if args.build_command:
        overrides["build_command"] = args.build_command
    if args.db_path:
        overrides["db_path"] = args.db_path
    return merge_config(base, overrides)


def cmd_scan(args: argparse.Namespace) -> int:
    config = _scan_config(args.repo, args)
    engine = Engine(config)
    try:
        signals = engine.scan(
            args.repo,
            allow_codeql_build=bool(getattr(args, "allow_codeql_build", False)),
        )
    except Exception as exc:
        from doc_engine.scanning.spring import CodeQLScannerError

        if isinstance(exc, CodeQLScannerError):
            print(f"error: {exc}", file=sys.stderr)
            return 1
        raise
    _save_json(args.out, signals)
    print(f"Wrote signals to {args.out}")
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    signals = _load_json(args.signals)
    interview = _load_json(args.interview) if args.interview else {}
    engine = Engine()
    bundle = engine.generate_docs(signals, interview_answers=interview)
    _save_json(args.out, bundle)
    print(f"Wrote docs bundle to {args.out}")
    return 0


def cmd_site(args: argparse.Namespace) -> int:
    bundle = _load_json(args.docs)
    engine = Engine()
    site_path = engine.build_site(bundle, out_dir=args.out_dir, site_name=args.site_name)
    print(f"Built site at {site_path}")
    return 0


def cmd_pipeline_run(args: argparse.Namespace) -> int:
    return run_pipeline(args)


def cmd_pipeline_gates(args: argparse.Namespace) -> int:
    from doc_engine.pipeline.live_gates import main as gates_main

    argv = [
        "--out-dir",
        args.out_dir,
        "--target-repo",
        args.target_repo,
    ]
    if args.docs_dir:
        argv.extend(["--docs-dir", args.docs_dir])
    if getattr(args, "compliance_profile", None):
        argv.extend(["--compliance-profile", args.compliance_profile])
    if args.strict_citations:
        argv.append("--strict-citations")
    if args.no_write_check:
        argv.append("--no-write-check")
    return gates_main(argv)


def cmd_certification_verify(args: argparse.Namespace) -> int:
    from doc_engine.tools.certification import main as cert_main

    argv = [args.path]
    if getattr(args, "allow_mock", False):
        argv.append("--allow-mock")
    return cert_main(argv)


def cmd_query(args: argparse.Namespace) -> int:
    """Facade: ``doc-engine query <kind> …`` → tools.query_artifacts."""
    from doc_engine.tools.query_artifacts import main as query_main

    argv = list(getattr(args, "query_argv", None) or [])
    return query_main(_without_argparse_separator(argv))


def _without_argparse_separator(argv: list[str]) -> list[str]:
    """Drop a leading ``--`` left over from argparse ``REMAINDER``."""
    parts = iter(argv)
    first = next(parts, None)
    if first is None:
        return []
    if first == "--":
        return list(parts)
    return [first, *parts]


def main() -> int:
    ap = argparse.ArgumentParser(prog="doc-engine", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    scan_ap = sub.add_parser("scan", help="Scan a repository and produce signals")
    scan_ap.add_argument("repo")
    scan_ap.add_argument(
        "--out",
        default="spring_signals.json",
        help="output path (default: spring_signals.json, same as Stage 0 / python -m doc_engine.tools.spring_signal_scan)",
    )
    scan_ap.add_argument(
        "--scanners",
        default=None,
        help="Comma-separated scanner names (overrides .doc-engine.yml)",
    )
    scan_ap.add_argument("--sql-dialect", default="ansi")
    scan_ap.add_argument("--respect-gitignore", action="store_true")
    scan_ap.add_argument("--build-command", default=None)
    scan_ap.add_argument("--db-path", default=None)
    scan_ap.add_argument(
        "--trust-repo-config",
        action="store_true",
        help=(
            "honor security-sensitive keys from the target repo's "
            ".doc-engine.yml (build_command, db_path, scanners, weakened "
            "compliance_profile). Default: treat that file as untrusted."
        ),
    )
    scan_ap.add_argument(
        "--allow-codeql-build",
        action="store_true",
        help=(
            "permit CodeQL database create --command against this tree. "
            "Required when --scanners includes codeql; only use for first-party "
            "repos or a sandboxed host."
        ),
    )
    scan_ap.set_defaults(func=cmd_scan)

    docs_ap = sub.add_parser(
        "docs",
        help="Placeholder docs bundle from signals (prefer: doc-engine pipeline run)",
    )
    docs_ap.add_argument("signals")
    docs_ap.add_argument("--out", default="docs.json")
    docs_ap.add_argument("--interview", default=None, help="Path to interview answers JSON")
    docs_ap.set_defaults(func=cmd_docs)

    site_ap = sub.add_parser("site", help="Build a static site from a docs bundle")
    site_ap.add_argument("docs")
    site_ap.add_argument("--out-dir", required=True)
    site_ap.add_argument("--site-name", default="Documentation")
    site_ap.set_defaults(func=cmd_site)

    pipeline_ap = sub.add_parser(
        "pipeline",
        help="Run the document-spring-repo pipeline (deterministic + optional gates)",
    )
    pipeline_sub = pipeline_ap.add_subparsers(dest="pipeline_command", required=True)
    run_ap = pipeline_sub.add_parser(
        "run",
        help="Run locally against one target repo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Deterministic stages use the package/scripts toolchain; "
               "Stages 1–4 are mocked unless you drive generative work via an "
               "external adapter (Claude, Cursor, etc.). Use --until STAGE to "
               "truncate the graph from build_stage_specs().",
    )
    add_run_arguments(run_ap)
    run_ap.set_defaults(func=cmd_pipeline_run)

    gates_ap = pipeline_sub.add_parser(
        "gates",
        help="Run mechanical gates on an existing run dir after live generative stages",
    )
    gates_ap.add_argument("--out-dir", required=True)
    gates_ap.add_argument("--target-repo", required=True)
    gates_ap.add_argument("--docs-dir", default=None)
    gates_ap.add_argument(
        "--compliance-profile",
        choices=["scan_only", "deterministic_only", "certified"],
        default=None,
        help="compliance profile (default: certified, or .doc-engine.yml). "
             "certified enables strict citation_coverage.",
    )
    gates_ap.add_argument("--strict-citations", action="store_true")
    gates_ap.add_argument("--no-write-check", action="store_true")
    gates_ap.set_defaults(func=cmd_pipeline_gates)

    cert_ap = sub.add_parser(
        "certification",
        help="Certification gate utilities",
    )
    cert_sub = cert_ap.add_subparsers(dest="certification_command", required=True)
    verify_ap = cert_sub.add_parser(
        "verify",
        help="Exit 0 only when certification.json reports certified: true",
    )
    verify_ap.add_argument(
        "path",
        nargs="?",
        default="certification.json",
        help="path to certification.json",
    )
    verify_ap.add_argument(
        "--allow-mock",
        action="store_true",
        help="accept generative_executor none/mock (default: require live)",
    )
    verify_ap.set_defaults(func=cmd_certification_verify)

    query_ap = sub.add_parser(
        "query",
        help=(
            "Typed read views over Stage-0 artifacts "
            "(evidence|routes|facts|entity|dependents|route-trace)"
        ),
    )
    query_ap.add_argument(
        "query_argv",
        nargs=argparse.REMAINDER,
        help="kind and flags — see: python -m doc_engine.tools.query_artifacts -h",
    )
    query_ap.set_defaults(func=cmd_query)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
