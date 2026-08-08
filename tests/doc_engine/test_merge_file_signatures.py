"""Tests for Path A file_signatures merge honesty."""

import logging
import unittest

from doc_engine.scanning._merge_signals import _merge_file_signatures


class MergeFileSignaturesTest(unittest.TestCase):
    def test_conflict_keeps_first_and_logs_warning(self):
        partials = [
            {"file_signatures": {"a.java": "aaa"}},
            {"file_signatures": {"a.java": "bbb"}},
        ]
        with self.assertLogs("doc_engine.scanning._merge_signals", level=logging.WARNING) as cm:
            merged = _merge_file_signatures(partials)
        self.assertEqual(merged["a.java"], "aaa")
        self.assertTrue(any("file_signatures conflict" in msg for msg in cm.output))


if __name__ == "__main__":
    unittest.main()
