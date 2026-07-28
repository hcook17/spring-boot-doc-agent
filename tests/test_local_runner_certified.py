"""Focused integration test for certified mock profile via local_runner."""

import json
import os
import tempfile
import unittest
from argparse import Namespace

from tests.conftest import FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH


class CertifiedMockIntegrationTest(unittest.TestCase):
    def test_certified_mock_profile_with_fixture_signals(self):
        from doc_engine.pipeline.local_runner import run_pipeline

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "run")
            args = Namespace(
                repo_path=str(FIXTURE_DIR),
                out_dir=out_dir,
                max_tokens=120000,
                docs_in_target_repo=False,
                prior_signals=None,
                skip_drift=True,
                respect_gitignore=False,
                strict_citations=False,
                keep_going=False,
                compliance_profile="certified",
                deterministic_only=False,
                signals_file=str(FIXTURE_SNAPSHOT_PATH),
            )
            code = run_pipeline(args)
            cert_path = os.path.join(out_dir, "certification.json")
            self.assertTrue(os.path.isfile(cert_path))
            with open(cert_path, encoding="utf-8") as f:
                cert = json.load(f)
            self.assertEqual(cert["compliance_profile"], "certified")
            self.assertTrue(cert["certified"])
            self.assertEqual(cert.get("generative_executor"), "mock")
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
