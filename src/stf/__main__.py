"""CLI: python -m stf …"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stf.adapters.gh_handoff import handoff_gh, write_handoff_checklist
from stf.ingest.review import findings_to_spec_seed, ingest_review_path
from stf.runners.implement import constitution_excerpts, plan_gate, run_waves, verify_gate
from stf.runners.store import SpecStore, TasksStore, write_change_pack
from stf.schemas.tasks import LedgerState, TaskBlock, TasksDocument
from stf.validators.lint_tasks import lint_summary, lint_tasks_document, mutate_tasks


def _cmd_ingest(args: argparse.Namespace) -> int:
    findings = ingest_review_path(Path(args.review))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = [f.model_dump(mode="json") for f in findings]
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.spec_dir:
        seed = findings_to_spec_seed(
            findings, target=args.target, source_review=str(args.review)
        )
        store = SpecStore(Path(args.spec_dir))
        store.write_spec(seed)
        write_change_pack(
            Path(args.spec_dir),
            added=[f"{f.id}: {f.title}" for f in findings if f.id.startswith("C")],
            modified=[f"{f.id}: {f.title}" for f in findings if f.id.startswith(("H", "N"))],
            removed=["Caller-supplied MCP root", "AssumeIndexed as default freshness lie"],
        )
    print(json.dumps({"findings": len(findings), "out": str(out)}, indent=2))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    store = TasksStore(Path(args.target_dir))
    tasks = store.load_tasks()
    spec = None
    spec_path = Path(args.target_dir) / "SPEC.json"
    if spec_path.is_file():
        spec = SpecStore(Path(args.target_dir)).load_spec()
    results = lint_tasks_document(tasks, spec, root=Path(args.root) if args.root else None)
    summary = lint_summary(results)
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


def _cmd_plan_gate(args: argparse.Namespace) -> int:
    store = TasksStore(Path(args.target_dir))
    tasks = store.load_tasks()
    spec = SpecStore(Path(args.target_dir)).load_spec() if (Path(args.target_dir) / "SPEC.json").is_file() else None
    try:
        result = plan_gate(tasks, spec)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, "waves": result["waves"], "finding_coverage": result["finding_coverage"]}))
    return 0


def _cmd_seed_tasks(args: argparse.Namespace) -> int:
    """Create a minimal valid TASKS.json from SPEC for remediation targets."""
    spec = SpecStore(Path(args.target_dir)).load_spec()
    tasks_list = [
        TaskBlock(
            id="T0",
            title="Pre-flight probes",
            goal="Reproduce critical findings with fail bars",
            inputs=[{"origin": "new", "datum": "probe harness"}],
            depends=[],
            gates=[f"INV-{fid}" for fid in spec.finding_ids if fid.startswith("C")][:3] or [],
            tests="Record baseline pytest node ids for C1/C2",
            verify="python -m pytest tests/doc_engine/test_query_artifacts.py -q --collect-only",
            acceptance="Critical probes documented; suite baseline recorded",
            data_modeling="n/a — probe",
            locate="n/a",
            implement="n/a — probe only",
        )
    ]
    wave1_deps = ["T0"]
    for i, row in enumerate(spec.inventory[:8], start=1):
        tid = f"T{i}"
        tasks_list.append(
            TaskBlock(
                id=tid,
                title=row.data_need[:80],
                goal=f"Address {row.id}",
                inputs=[{"origin": row.id, "datum": row.data_need}],
                depends=list(wave1_deps),
                tests=f"Deviation test for {row.id}",
                verify=f"python -m pytest tests/stf -q -k {row.id.replace('-', '_')}",
                acceptance=f"{row.id} remediated",
                locate=row.origin if "/" in row.origin else "src/doc_engine/query/",
                implement=f"Fix {row.id}",
                data_modeling="n/a",
            )
        )
    doc = TasksDocument(
        target=spec.target,
        source_spec=str(Path(args.target_dir) / "SPEC.md"),
        why_this_order="T0 probes first; inventory remediation depends on T0; critical before polish.",
        decisions=spec.decisions,
        tasks=tasks_list,
        ledger=LedgerState.PLAN,
    )
    TasksStore(Path(args.target_dir)).write_tasks(doc)
    print(json.dumps({"tasks": len(tasks_list), "target": spec.target}))
    return 0


def _cmd_implement(args: argparse.Namespace) -> int:
    store = TasksStore(Path(args.target_dir))
    if args.plan_gate:
        spec = SpecStore(Path(args.target_dir)).load_spec()
        plan_gate(store.load_tasks(), spec)
    result = run_waves(store, start_wave=args.resume_wave)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_reviewer_token(args: argparse.Namespace) -> int:
    store = TasksStore(Path(args.target_dir))
    token = store.issue_validation_token()
    print(json.dumps({"validation_token": token}))
    return 0


def _cmd_mark_done(args: argparse.Namespace) -> int:
    store = TasksStore(Path(args.target_dir))
    try:
        store.mark_done(validation_token=args.token)
    except PermissionError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, "ledger": "done"}))
    return 0


def _cmd_handoff(args: argparse.Namespace) -> int:
    store = TasksStore(Path(args.target_dir))
    tasks = store.load_tasks()
    if args.checklist:
        path = write_handoff_checklist(Path(args.checklist), tasks)
        print(json.dumps({"checklist": str(path)}))
    else:
        created = handoff_gh(tasks, dry_run=not args.create)
        print(json.dumps(created, indent=2))
    return 0


def _cmd_constitution(args: argparse.Namespace) -> int:
    text = constitution_excerpts(Path(args.repo_root))
    Path(args.out).write_text(text, encoding="utf-8")
    print(json.dumps({"chars": len(text), "out": args.out}))
    return 0


def _cmd_mutate(args: argparse.Namespace) -> int:
    store = TasksStore(Path(args.target_dir))
    mutated = mutate_tasks(store.load_tasks(), args.mode)
    out = Path(args.out) if args.out else Path(args.target_dir) / f"TASKS.mutant.{args.mode}.json"
    out.write_text(mutated.model_dump_json(indent=2), encoding="utf-8")
    results = lint_tasks_document(mutated)
    summary = lint_summary(results)
    print(json.dumps({"mode": args.mode, "lint_ok": summary["ok"], "fail": summary["fail"]}))
    # mutants should fail lint
    return 0 if not summary["ok"] else 1


def _cmd_verify_gate(args: argparse.Namespace) -> int:
    cmds = args.cmd or []
    try:
        result = verify_gate(verify_commands=cmds)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stf", description="Spec Task Framework CLI")
    sub = p.add_subparsers(dest="command", required=True)

    ing = sub.add_parser("ingest-review", help="Review MD → Findings JSON (+ optional SPEC seed)")
    ing.add_argument("--review", required=True)
    ing.add_argument("--out", required=True)
    ing.add_argument("--spec-dir")
    ing.add_argument("--target", default="pr-94-query-surface")
    ing.set_defaults(func=_cmd_ingest)

    val = sub.add_parser("validate", help="Lint TASKS.json (+ SPEC.json)")
    val.add_argument("--target-dir", required=True)
    val.add_argument("--root", help="fixture root for Locate anchors")
    val.set_defaults(func=_cmd_validate)

    pg = sub.add_parser("plan-gate", help="SPOQ plan gate before Wave 1")
    pg.add_argument("--target-dir", required=True)
    pg.set_defaults(func=_cmd_plan_gate)

    st = sub.add_parser("seed-tasks", help="Seed TASKS.json from SPEC.json")
    st.add_argument("--target-dir", required=True)
    st.set_defaults(func=_cmd_seed_tasks)

    imp = sub.add_parser("implement", help="Run topological waves")
    imp.add_argument("--target-dir", required=True)
    imp.add_argument("--plan-gate", action="store_true")
    imp.add_argument("--resume-wave", type=int, default=None)
    imp.set_defaults(func=_cmd_implement)

    tok = sub.add_parser("reviewer-token", help="Issue 2+N validation token")
    tok.add_argument("--target-dir", required=True)
    tok.set_defaults(func=_cmd_reviewer_token)

    done = sub.add_parser("mark-done", help="Mark DONE with Reviewer token")
    done.add_argument("--target-dir", required=True)
    done.add_argument("--token", required=True)
    done.set_defaults(func=_cmd_mark_done)

    ho = sub.add_parser("handoff-gh", help="Create gh issues or checklist")
    ho.add_argument("--target-dir", required=True)
    ho.add_argument("--create", action="store_true", help="actually call gh")
    ho.add_argument("--checklist", help="write markdown checklist path")
    ho.set_defaults(func=_cmd_handoff)

    con = sub.add_parser("constitution", help="Emit CONSTRAINTS+CLAUDE excerpts")
    con.add_argument("--repo-root", default=".")
    con.add_argument("--out", required=True)
    con.set_defaults(func=_cmd_constitution)

    mut = sub.add_parser("mutate", help="Apply named lint mutant")
    mut.add_argument("--target-dir", required=True)
    mut.add_argument("--mode", required=True)
    mut.add_argument("--out")
    mut.set_defaults(func=_cmd_mutate)

    vg = sub.add_parser("verify-gate", help="Run verify gate (dry-run if no exec)")
    vg.add_argument("--cmd", action="append", default=[])
    vg.set_defaults(func=_cmd_verify_gate)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
