"""Unit tests for doc_engine.real_fixture + anonymized gap baseline shape."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from doc_engine.paths import repo_root
from doc_engine.real_fixture import (
    ENV_REAL_REPO,
    generative_paths_require_artifacts,
    real_artifacts_dir,
    real_repo_path,
    require_real_repo,
    stage0_paths_require_real_repo,
)

REPO_ROOT = repo_root()
BASELINE = REPO_ROOT / "scripts" / "coverage" / "real_repo_gap_baseline.json"
SHAPES_DIR = REPO_ROOT / "scripts" / "fixtures" / "gap_probe_shapes"


class RealFixtureResolverTest(unittest.TestCase):
    def test_canonical_repo_env(self):
        with mock.patch.dict(
            os.environ,
            {ENV_REAL_REPO: "/tmp/local-spring-tree"},
            clear=False,
        ):
            for legacy in (
                "GAP_PROBE_OCS_REPO",
                "DRIFT_OCS_REPO",
                "PARTITION_REPO_REAL_FIXTURE_DIR",
            ):
                os.environ.pop(legacy, None)
            self.assertEqual(real_repo_path(), Path("/tmp/local-spring-tree"))

    def test_legacy_gap_probe_alias(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_REAL_REPO, None)
            os.environ["GAP_PROBE_OCS_REPO"] = "/tmp/via-legacy"
            for other in ("DRIFT_OCS_REPO", "PARTITION_REPO_REAL_FIXTURE_DIR"):
                os.environ.pop(other, None)
            self.assertEqual(real_repo_path(), Path("/tmp/via-legacy"))

    def test_require_real_repo_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for name in (
                ENV_REAL_REPO,
                "GAP_PROBE_OCS_REPO",
                "DRIFT_OCS_REPO",
                "PARTITION_REPO_REAL_FIXTURE_DIR",
                "KITCHEN_SINK_REPO",
            ):
                os.environ.pop(name, None)
            with mock.patch(
                "doc_engine.real_fixture._read_path_file", return_value=None
            ):
                with self.assertRaises(FileNotFoundError):
                    require_real_repo()

    def test_path_file_resolves_when_env_unset(self):
        pointer = REPO_ROOT / "local-runs" / "_test_real_repo_pointer"
        pointer.parent.mkdir(parents=True, exist_ok=True)
        target = Path("/tmp/path-file-spring-tree")
        with mock.patch.dict(os.environ, {}, clear=False):
            for name in (
                ENV_REAL_REPO,
                "GAP_PROBE_OCS_REPO",
                "DRIFT_OCS_REPO",
                "PARTITION_REPO_REAL_FIXTURE_DIR",
                "KITCHEN_SINK_REPO",
            ):
                os.environ.pop(name, None)
            with mock.patch(
                "doc_engine.real_fixture.REAL_REPO_PATH_FILE",
                Path("local-runs") / "_test_real_repo_pointer",
            ):
                pointer.write_text(
                    f"# comment\n{target}\n", encoding="utf-8"
                )
                try:
                    self.assertEqual(real_repo_path(), target)
                finally:
                    pointer.unlink(missing_ok=True)

    def test_stage0_path_prefixes(self):
        self.assertTrue(
            stage0_paths_require_real_repo(["src/doc_engine/scanning/gap_probe.py"])
        )
        self.assertTrue(
            stage0_paths_require_real_repo(
                ["tests/doc_engine/test_gap_probe_ocs_real_world.py"]
            )
        )
        self.assertFalse(stage0_paths_require_real_repo(["README.md"]))
        self.assertFalse(stage0_paths_require_real_repo(["scripts/ci/pre_pr.py"]))

    def test_generative_path_prefixes(self):
        self.assertTrue(
            generative_paths_require_artifacts(["src/doc_engine/pipeline/stages.py"])
        )
        self.assertFalse(generative_paths_require_artifacts(["README.md"]))

    def test_artifacts_relative_resolves_under_repo(self):
        with mock.patch.dict(
            os.environ,
            {"DOC_ENGINE_REAL_ARTIFACTS_DIR": "local-runs/real-repo-latest"},
            clear=False,
        ):
            path = real_artifacts_dir()
        self.assertEqual(path, REPO_ROOT / "local-runs" / "real-repo-latest")


class AnonymizedGapBaselineTest(unittest.TestCase):
    def test_baseline_shape(self):
        data = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["corpus"], "external-dev-corpus")
        for key in ("R_sym_min", "R_coll_max", "R_join_min", "U_max"):
            self.assertIn(key, data["bands"])
        self.assertEqual(data["expected"]["lineage_dominant_stratum"], "dialect_or_syntax")
        # Non-vacuous bands (adversarial: [0,1] / U_max=1 accepted anything).
        self.assertGreater(data["bands"]["R_lin_mean_min"], 0.0)
        self.assertLess(data["bands"]["R_lin_mean_max"], 1.0)
        self.assertLess(data["bands"]["U_max"], 1.0)
        # Confidentiality: baseline must not contain denylist tokens.
        # Load from the denylist SoT — never embed forbidden strings here.
        denylist_path = REPO_ROOT / "scripts" / "ci" / "client_identifier_denylist.txt"
        tokens = [
            line.strip()
            for line in denylist_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertTrue(tokens, "denylist must have at least one token")
        blob = BASELINE.read_text(encoding="utf-8")
        for token in tokens:
            self.assertNotIn(token, blob)

    def test_hermetic_shapes_exist(self):
        shapes = sorted(SHAPES_DIR.glob("*.json"))
        self.assertGreaterEqual(len(shapes), 3)
        for path in shapes:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("intent", payload)
            self.assertIn("signals", payload)
            self.assertIn("expect", payload)


if __name__ == "__main__":
    unittest.main()
