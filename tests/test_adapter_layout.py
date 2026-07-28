"""Smoke tests for Claude adapter layout and GitHub action.yml contract."""

import json
import os
import unittest
from pathlib import Path

from doc_engine.paths import repo_root


class ClaudeAdapterLayoutTest(unittest.TestCase):
    def test_marketplace_points_at_adapters_claude(self):
        marketplace = json.loads(
            (repo_root() / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        plugins = marketplace.get("plugins") or []
        self.assertTrue(plugins)
        source = plugins[0].get("source")
        self.assertEqual(source, "./adapters/claude")

    def test_claude_plugin_and_hooks_resolve(self):
        adapter = repo_root() / "adapters" / "claude"
        self.assertTrue((adapter / "plugin.json").is_file())
        hooks = json.loads((adapter / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        for entry in hooks.get("hooks", {}).get("PreToolUse", []):
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                if "${CLAUDE_PLUGIN_ROOT}" in cmd:
                    rel = cmd.split("${CLAUDE_PLUGIN_ROOT}")[1].strip().strip('"')
                    rel = rel.replace("/hooks/", "hooks/").lstrip("/")
                    if rel.startswith("hooks/"):
                        path = adapter / rel.replace("/", os.sep)
                        self.assertTrue(path.is_file(), f"missing hook script: {path}")


class GitHubActionContractTest(unittest.TestCase):
    def test_root_action_yml_declares_certification_outputs(self):
        text = (repo_root() / "action.yml").read_text(encoding="utf-8")
        self.assertIn("certification-path", text)
        self.assertIn("certified", text)
        self.assertIn("pipeline run", text)
        self.assertIn("doc-engine certification verify", text)
        self.assertNotIn("adapters/github/action.yml", text)

    def test_adapters_github_has_readme_not_duplicate_action(self):
        github_adapter = repo_root() / "adapters" / "github"
        self.assertTrue((github_adapter / "README.md").is_file())
        self.assertFalse((github_adapter / "action.yml").exists())


if __name__ == "__main__":
    unittest.main()
