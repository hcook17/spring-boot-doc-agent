#!/usr/bin/env python3
"""Tests for the doc_engine SDK package."""

import json
import os
import sys
import tempfile
import unittest
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

class ConfigLoaderTest(unittest.TestCase):
    def test_load_json_config(self):
        from doc_engine.config_loader import load_repo_config

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = os.path.join(tmp, ".doc-engine.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump({"scanners": ["filesystem"], "sql_dialect": "mysql"}, f)
            cfg = load_repo_config(tmp)
            self.assertIsNotNone(cfg)
            self.assertEqual(cfg.scanners, ["filesystem"])
            self.assertEqual(cfg.sql_dialect, "mysql")

    def test_missing_config_returns_none(self):
        from doc_engine.config_loader import load_repo_config

        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_repo_config(tmp))


class EngineSmokeTest(unittest.TestCase):
    def test_scan_filesystem_only(self):
        from doc_engine import Engine, Config

        engine = Engine(Config(scanners=["filesystem"]))
        signals = engine.scan(str(FIXTURE_DIR))
        self.assertEqual(signals["schema_version"], 7)
        self.assertIn("file_signatures", signals)
        self.assertGreater(signals["files_scanned"]["java"], 0)

    def test_generate_docs_produces_fourteen_files(self):
        from doc_engine import Engine, Config

        engine = Engine(Config(scanners=["filesystem"]))
        signals = engine.scan(str(FIXTURE_DIR))
        bundle = engine.generate_docs(signals)
        self.assertIn("docs", bundle)
        self.assertEqual(len(bundle["docs"]), 14)
        self.assertTrue(all(name.endswith(".md") for name in bundle["docs"]))

    def test_build_site_writes_output(self):
        from doc_engine import Engine, Config

        engine = Engine(Config(scanners=["filesystem"]))
        signals = engine.scan(str(FIXTURE_DIR))
        bundle = engine.generate_docs(signals)
        with tempfile.TemporaryDirectory() as tmp:
            site_path = engine.build_site(bundle, out_dir=tmp, site_name="Test")
            self.assertTrue(os.path.isdir(site_path))
            self.assertTrue(any(f.endswith(".html") for f in os.listdir(site_path)))


class ScannerFrameworkExportTest(unittest.TestCase):
    def test_scanner_protocols_importable(self):
        from doc_engine.scanner import Scanner, Merger, LineageResolver, get_scanner

        scanner = get_scanner("filesystem")
        self.assertEqual(scanner.name, "filesystem")


if __name__ == "__main__":
    unittest.main()
