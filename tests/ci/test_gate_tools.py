"""Tests for scripts/ci/gate_tools.py — portable quality-gate CLI resolution."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gate_tools


class GateToolsTest(unittest.TestCase):
    def test_python_module_command_uses_sys_executable(self) -> None:
        cmd = gate_tools.python_module_command("tach", "check")
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(cmd[1:3], ["-m", "tach"])
        self.assertEqual(cmd[3:], ["check"])

    def test_jscpd_prefers_native_binary_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_bin = Path(tmp) / "jscpd"
            fake_bin.write_text("", encoding="utf-8")
            with mock.patch.object(
                gate_tools,
                "_jscpd_native_candidates",
                return_value=[fake_bin],
            ):
                cmd = gate_tools.jscpd_command("--threshold=3", "a.py")
            self.assertEqual(cmd[0], str(fake_bin))
            self.assertEqual(cmd[1:], ["--threshold=3", "a.py"])

    def test_jscpd_falls_back_to_node_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrapper = root / "node_modules" / "jscpd" / "run-jscpd.js"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text("#!/usr/bin/env node\n", encoding="utf-8")
            with (
                mock.patch.object(gate_tools, "REPO_ROOT", root),
                mock.patch.object(
                    gate_tools,
                    "_jscpd_native_candidates",
                    return_value=[],
                ),
                mock.patch.object(
                    gate_tools,
                    "require_on_path",
                    return_value="/usr/bin/node",
                ),
            ):
                cmd = gate_tools.jscpd_command("--format=python")
            self.assertEqual(cmd[0], "/usr/bin/node")
            self.assertEqual(cmd[1], str(wrapper))
            self.assertEqual(cmd[2:], ["--format=python"])

    def test_jscpd_missing_install_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch.object(gate_tools, "REPO_ROOT", root),
                mock.patch.object(
                    gate_tools,
                    "_jscpd_native_candidates",
                    return_value=[],
                ),
                self.assertRaises(SystemExit) as ctx,
            ):
                gate_tools.jscpd_command()
            self.assertEqual(ctx.exception.code, 2)

    def test_require_on_path_checks_venv_sibling(self) -> None:
        sibling = Path(sys.executable).resolve().parent
        name = "diff-cover.exe" if os.name == "nt" else "diff-cover"
        fake = sibling / name

        def fake_is_file(self: Path) -> bool:
            return self == fake or str(self) == str(fake)

        with (
            mock.patch.object(gate_tools.shutil, "which", return_value=None),
            mock.patch.object(Path, "is_file", fake_is_file),
        ):
            resolved = gate_tools.require_on_path("diff-cover")
        self.assertEqual(resolved, str(fake))


if __name__ == "__main__":
    unittest.main(verbosity=2)
