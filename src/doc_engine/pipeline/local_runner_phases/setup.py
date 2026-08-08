"""Phase 1: resolve paths, trust, profile, out_dir, Log/Runner, signals reuse."""

from __future__ import annotations

import datetime
import os
import shutil
import sys

from doc_engine.config.loader import load_repo_config
from doc_engine.pipeline.compliance import (
    ComplianceProfile,
    citations_are_strict,
    resolve_compliance_profile,
)
from doc_engine.pipeline.local_runner_phases.state import LocalRunState
from doc_engine.pipeline.local_runner_phases.support import Log, Runner


def _require_repo_dir(repo_path: str) -> int | None:
    if os.path.isdir(repo_path):
        return None
    print(f"error: {repo_path} is not a directory", file=sys.stderr)
    return 2


def _resolve_run_policy(args, repo_path: str):
    from doc_engine.config.repo_trust import sanitize_repo_settings, trust_from_flag

    trust = trust_from_flag(bool(getattr(args, "trust_repo_config", False)))
    repo_config = sanitize_repo_settings(load_repo_config(repo_path), trust)
    profile = resolve_compliance_profile(repo_config, args)
    allow_mock = bool(getattr(args, "allow_mock", False))
    skip_signal_scan = bool(args.signals_file)
    strict_citations_effective = citations_are_strict(
        profile, force_strict=args.strict_citations
    )
    return profile, allow_mock, skip_signal_scan, strict_citations_effective


def _resolve_out_paths(args, repo_path: str) -> tuple[str, str, str]:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = args.out_dir or os.path.join(
        os.getcwd(),
        "local-runs",
        f"{os.path.basename(repo_path.rstrip(os.sep))}-{stamp}",
    )
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    docs_dir = (
        os.path.join(repo_path, "docs")
        if args.docs_in_target_repo
        else os.path.join(out_dir, "docs")
    )
    today = datetime.date.today().isoformat()
    return out_dir, docs_dir, today


def phase_setup(args) -> LocalRunState | int:
    """Prepare run directories and logging. Returns exit code 2 on hard errors."""
    repo_path = os.path.abspath(args.repo_path)
    if (err := _require_repo_dir(repo_path)) is not None:
        return err

    profile, allow_mock, skip_signal_scan, strict_citations_effective = (
        _resolve_run_policy(args, repo_path)
    )
    out_dir, docs_dir, today = _resolve_out_paths(args, repo_path)

    log = Log(os.path.join(out_dir, "run.log"))
    runner = Runner(log, args.keep_going)
    py = sys.executable
    manifest = os.path.join(out_dir, "run_manifest.json")
    signals_path = os.path.join(out_dir, "spring_signals.json")
    preflight_path = os.path.join(out_dir, "capacity_preflight_report.json")

    if args.signals_file:
        err = _reuse_signals_file(args, log, signals_path, out_dir)
        if err is not None:
            return err

    _log_run_banner(args, log, repo_path, out_dir, docs_dir, py, profile, today)

    return LocalRunState(
        args=args,
        repo_path=repo_path,
        out_dir=out_dir,
        docs_dir=docs_dir,
        today=today,
        profile=profile,
        allow_mock=allow_mock,
        skip_signal_scan=skip_signal_scan,
        strict_citations_effective=strict_citations_effective,
        log=log,
        runner=runner,
        py=py,
        manifest=manifest,
        signals_path=signals_path,
        preflight_path=preflight_path,
        until_stage=getattr(args, "until", None),
    )


def _reuse_signals_file(args, log, signals_path: str, out_dir: str) -> int | None:
    signals_src = os.path.abspath(args.signals_file)
    if not os.path.isfile(signals_src):
        print(f"error: --signals-file not found: {signals_src}", file=sys.stderr)
        return 2
    shutil.copy2(signals_src, signals_path)
    log(f"  reused signals: {signals_src} -> {signals_path}")
    from doc_engine.scanning.stage0_siblings import (
        Stage0SiblingError,
        materialize_stage0_siblings,
    )

    try:
        materialize_stage0_siblings(signals_src, out_dir)
    except Stage0SiblingError as exc:
        print(
            f"error: --signals-file reuse cannot prepare Stage-0 siblings: {exc}",
            file=sys.stderr,
        )
        return 2
    log("  reused Path A siblings: facts.jsonl + covering_proof.json")
    return None


def _log_run_banner(args, log, repo_path, out_dir, docs_dir, py, profile, today) -> None:
    log.rule("document-spring-repo — LOCAL END-TO-END RUN")
    log(f"  target repo   : {repo_path}")
    log(f"  artifacts     : {out_dir}")
    log(
        f"  docs output   : {docs_dir}"
        f"{'  (inside the target repo)' if args.docs_in_target_repo else '  (outside the target repo)'}"
    )
    log(f"  python        : {py}")
    log(f"  compliance    : {profile.value}")
    if args.signals_file:
        log(
            f"  signals file  : {os.path.abspath(args.signals_file)} "
            f"(signal_scan skipped)"
        )
    else:
        log(
            f"  ast-grep      : "
            f"{shutil.which('ast-grep') or 'NOT ON PATH — the signal scan will fail'}"
        )
    log(f"  mode          : {profile.value}")
    log(f"  date          : {today}")
    log("")
    if profile == ComplianceProfile.SCAN_ONLY:
        log("  Scan-only profile — init_manifest and signal_scan only.")
    elif profile == ComplianceProfile.DETERMINISTIC_ONLY:
        log("  Deterministic stages only — no mocked LLM stages or doc gates.")
    else:
        log("  Stages 1-4 are MOCKED — no model runs. Their artifacts are")
        log("  shape-faithful and their citations resolve, but the prose is")
        log("  templated and documents nothing. Everything else is the real script.")
