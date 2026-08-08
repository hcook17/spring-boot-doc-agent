"""Portable Stage 0: package module ports, not monorepo scripts/ paths."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from doc_engine.pipeline.context import PipelineContext, StageKind
from doc_engine.pipeline.stages import build_stage_specs

from tests.conftest import FIXTURE_DIR


def _minimal_context(out: Path) -> PipelineContext:
    return PipelineContext(
        repo_path=Path(FIXTURE_DIR),
        out_dir=out,
        manifest_path=out / "run_manifest.json",
        docs_dir=out / "docs",
        python=sys.executable,
        today="2026-07-29",
        log=lambda *_a, **_k: None,
    )


class StageSpecPortabilityTest(unittest.TestCase):
    def test_deterministic_stages_use_package_modules(self):
        out = Path(tempfile.mkdtemp())
        ctx = _minimal_context(out)
        for spec in build_stage_specs():
            if spec.kind != StageKind.DETERMINISTIC:
                continue
            self.assertIsNotNone(spec.argv_builder, spec.name)
            argv = spec.argv_builder(ctx)
            self.assertIn("-m", argv, msg=f"{spec.name}: {argv}")
            mod = argv[argv.index("-m") + 1]
            self.assertTrue(
                mod.startswith("doc_engine.tools."),
                msg=f"{spec.name} module={mod}",
            )
            # No argv element may be a path into scripts/*.py as the tool entry.
            for arg in argv:
                if arg.endswith(".py"):
                    self.fail(f"{spec.name} still invokes script path: {arg}")


class WheelWithoutScriptsSmokeTest(unittest.TestCase):
    """Run deterministic Stage 0 with CWD outside the meta-repo (no scripts/ sibling)."""

    def test_deterministic_only_against_fixture_without_scripts_cwd(self):
        fixture = Path(FIXTURE_DIR)
        if not fixture.is_dir():
            self.skipTest("spring fixture missing")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            work = Path(tmp) / "cwd"
            work.mkdir()
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "doc_engine.cli",
                    "pipeline",
                    "run",
                    str(fixture),
                    "--out-dir",
                    str(out),
                    "--compliance-profile",
                    "deterministic_only",
                    "--skip-drift",
                ],
                cwd=str(work),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
            body = (proc.stdout or "") + (proc.stderr or "")
            self.assertEqual(
                proc.returncode,
                0,
                msg=f"exit={proc.returncode}\n{body[-4000:]}",
            )
            self.assertTrue((out / "spring_signals.json").is_file(), body[-2000:])
            self.assertTrue((out / "groups.json").is_file())
            self.assertTrue((out / "certification.json").is_file())


class GenerativeChoreographySoTTest(unittest.TestCase):
    def test_every_generative_stage_names_agents(self):
        from doc_engine.pipeline.stages import generative_choreography

        rows = generative_choreography()
        self.assertEqual(len(rows), 4)
        by_name = {r["name"]: r for r in rows}
        self.assertEqual(by_name["file_summarize"]["agents"], ["file-summarizer"])
        self.assertEqual(
            by_name["architect"]["agents"],
            ["architect-segment", "architect-merge"],
        )
        self.assertTrue(by_name["gap_analysis_interview"]["requires_human_interview"])
        self.assertIn("facts.jsonl", by_name["gap_analysis_interview"]["inputs"])
        self.assertIn("spring_signals.json", by_name["gap_analysis_interview"]["inputs"])
        self.assertEqual(by_name["doc_writer"]["agents"], ["doc-writer"])
        self.assertIn("facts.jsonl", by_name["doc_writer"]["inputs"])


if __name__ == "__main__":
    unittest.main()
