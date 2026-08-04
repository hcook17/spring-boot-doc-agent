"""Adapter packaging contracts for the A+C hybrid architecture.

Enforces:
- every ${CLAUDE_PLUGIN_ROOT}/… path cited in adapter skills/agents/hooks resolves
- no ${CLAUDE_PLUGIN_ROOT}/scripts (marketplace install has no scripts tree)
- skill-cited doc-engine pipeline/certification/scan commands answer --help
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

from doc_engine.paths import repo_root

PLUGIN_ROOT_REF = re.compile(
    r"\$\{CLAUDE_PLUGIN_ROOT\}(/[^\s`\"')]+)"
)
BANNED_SCRIPTS = "${CLAUDE_PLUGIN_ROOT}/scripts"
# Allowlisted doc-engine invocations skills may document (A+C facade).
ALLOWED_DOC_ENGINE_PREFIXES = (
    "doc-engine pipeline run",
    "doc-engine pipeline gates",
    "doc-engine certification verify",
    "doc-engine scan",
    "doc-engine --help",
    "doc-engine pipeline run --help",
)


def _adapter() -> Path:
    return repo_root() / "adapters" / "claude"


def _iter_adapter_text_files():
    adapter = _adapter()
    for pattern in ("skills/**/*.md", "agents/**/*.md", "hooks/**/*", "*.md", "plugin.json"):
        yield from adapter.glob(pattern)


class ClaudeAdapterPathResolveTest(unittest.TestCase):
    def test_marketplace_points_at_adapters_claude(self):
        marketplace = json.loads(
            (repo_root() / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        plugins = marketplace.get("plugins") or []
        self.assertTrue(plugins)
        self.assertEqual(plugins[0].get("source"), "./adapters/claude")

    def test_constraints_stub_exists(self):
        self.assertTrue((_adapter() / "CONSTRAINTS.md").is_file())

    def test_plugin_root_refs_resolve_under_adapter(self):
        adapter = _adapter()
        missing: list[str] = []
        for path in _iter_adapter_text_files():
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in PLUGIN_ROOT_REF.finditer(text):
                rel = match.group(1).lstrip("/")
                # Strip trailing punctuation leftover from prose, and JSON
                # escape backslashes left when scanning hooks.json as text
                # (raw `\"` → path ends with `\`).
                rel = rel.rstrip(".,;:`\"')\\")
                if rel.startswith("scripts/") or rel == "scripts":
                    continue  # covered by ban test
                target = adapter / rel.replace("/", os.sep)
                if not target.exists():
                    missing.append(f"{path.relative_to(repo_root())}: {match.group(0)}")
        self.assertEqual(missing, [], msg="unresolved CLAUDE_PLUGIN_ROOT paths:\n" + "\n".join(missing))

    def test_no_plugin_root_scripts_in_adapter_skills(self):
        hits: list[str] = []
        skills = _adapter() / "skills"
        for path in skills.rglob("*.md"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if BANNED_SCRIPTS in text:
                hits.append(str(path.relative_to(repo_root())))
            # Also ban bare python3 …/scripts when clearly plugin-rooted prose leftovers
            if 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/' in text:
                hits.append(str(path.relative_to(repo_root())))
        self.assertEqual(hits, [], msg="banned plugin scripts refs:\n" + "\n".join(hits))

    def test_hooks_resolve(self):
        adapter = _adapter()
        hooks = json.loads((adapter / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        for entry in hooks.get("hooks", {}).get("PreToolUse", []):
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                if "${CLAUDE_PLUGIN_ROOT}" not in cmd:
                    continue
                rel = cmd.split("${CLAUDE_PLUGIN_ROOT}")[1].strip().strip('"')
                rel = rel.replace("/hooks/", "hooks/").lstrip("/")
                if rel.startswith("hooks/"):
                    path = adapter / rel.replace("/", os.sep)
                    self.assertTrue(path.is_file(), f"missing hook script: {path}")

    def test_deny_hooks_are_wired_in_hooks_json(self):
        """deny_text_search / deny_raw_network must be listed (not only exist)."""
        adapter = _adapter()
        hooks = json.loads((adapter / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        commands = []
        for entry in hooks.get("hooks", {}).get("PreToolUse", []):
            for hook in entry.get("hooks", []):
                commands.append(hook.get("command", ""))
        joined = "\n".join(commands)
        self.assertIn("deny_text_search.py", joined)
        self.assertIn("deny_raw_network.py", joined)
        # pipe-exit lives in .claude/settings.json only — not plugin hooks.json
        self.assertNotIn("check_pipe_exit_code.py", joined)


class CliFacadeSmokeTest(unittest.TestCase):
    def _help(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "doc_engine.cli", *args],
            cwd=str(repo_root()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

    def test_pipeline_run_help(self):
        proc = self._help("pipeline", "run", "--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--until", proc.stdout)

    def test_pipeline_gates_help(self):
        proc = self._help("pipeline", "gates", "--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_certification_verify_help(self):
        proc = self._help("certification", "verify", "--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_scan_help_default_out(self):
        proc = self._help("scan", "--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("spring_signals.json", proc.stdout)


class SkillSourceOfTruthTest(unittest.TestCase):
    """Root skills/ is a synced mirror of adapters/claude/skills product skills."""

    PRODUCT_SKILLS = (
        "document-spring-repo",
        "capacity-preflight",
        "citation-coverage",
        "semantic-pipeline-eval",
    )

    def test_root_product_skills_match_adapter_sot(self):
        adapter = _adapter() / "skills"
        root = repo_root() / "skills"
        mismatches: list[str] = []
        for name in self.PRODUCT_SKILLS:
            for rel in (adapter / name).rglob("*"):
                if not rel.is_file():
                    continue
                suffix = rel.relative_to(adapter / name)
                other = root / name / suffix
                if not other.is_file():
                    mismatches.append(f"missing root mirror: skills/{name}/{suffix.as_posix()}")
                    continue
                if rel.read_bytes() != other.read_bytes():
                    mismatches.append(
                        f"drift: skills/{name}/{suffix.as_posix()} != "
                        f"adapters/claude/skills/{name}/{suffix.as_posix()}"
                    )
        self.assertEqual(
            mismatches,
            [],
            msg="skill SoT drift (edit adapters/claude/skills, then sync root skills/):\n"
            + "\n".join(mismatches),
        )

    def test_document_spring_repo_references_present_in_both_trees(self):
        for base in (_adapter() / "skills", repo_root() / "skills"):
            tax = base / "document-spring-repo" / "references" / "doc-taxonomy.md"
            self.assertTrue(tax.is_file(), f"missing {tax}")


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
