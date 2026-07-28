#!/usr/bin/env python3
"""Build a DeepWiki-like static site from the 14 generated markdown docs.

Expects a directory containing the fourteen-file taxonomy:
  readme.md, architecture.md, integrations.md, authorization.md, database.md,
  operations.md, observability.md, troubleshooting.md, configuration.md,
  change_impact.md, glossary.md, local_development.md, testing.md,
  known_limitations.md

Produces a self-contained MkDocs site in the output directory.

Usage:
    python3 scripts/build_docs_site.py --docs-dir <path> --out-dir <path>

Example from the repo root:
    python3 scripts/build_docs_site.py --docs-dir ocs-api-service-develop/docs --out-dir _site

The output directory can be served locally with:
    python3 -m http.server --directory <out-dir> 8000

Or deployed to GitHub Pages / Netlify / S3 as a static bundle.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional


# Order matches the 14-file taxonomy in skills/document-spring-repo/references/doc-taxonomy.md
NAV_ORDER = [
    ("readme.md", "Readme"),
    ("architecture.md", "Architecture"),
    ("integrations.md", "Integrations"),
    ("authorization.md", "Authorization"),
    ("database.md", "Database"),
    ("operations.md", "Operations"),
    ("observability.md", "Observability"),
    ("troubleshooting.md", "Troubleshooting"),
    ("configuration.md", "Configuration"),
    ("change_impact.md", "Change Impact"),
    ("glossary.md", "Glossary"),
    ("local_development.md", "Local Development"),
    ("testing.md", "Testing"),
    ("known_limitations.md", "Known Limitations"),
]


def _find_mkdocs_yml() -> Path:
    """Return the bundled mkdocs.yml template next to this script."""
    script_dir = Path(__file__).resolve().parent
    return script_dir / ".." / "site" / "mkdocs.yml"


def _build_nav(docs_dir: Path) -> List:
    """Build a MkDocs nav list from the 14-file taxonomy, skipping missing files."""
    nav = []
    for filename, title in NAV_ORDER:
        if (docs_dir / filename).is_file():
            nav.append({title: filename})
    return nav


def _yaml_nav(nav: List) -> str:
    """Serialize nav as a compact YAML fragment."""
    lines = []
    for entry in nav:
        for title, path in entry.items():
            lines.append(f"  - {title}: {path}")
    return "\n".join(lines)


def _write_mkdocs_config(work_dir: Path, docs_dir: Path, site_name: str, repo_url: Optional[str]) -> None:
    """Write a self-contained mkdocs.yml into the working directory."""
    nav = _build_nav(docs_dir)
    if not nav:
        raise RuntimeError(f"no recognized markdown files found in {docs_dir}")

    extra = ""
    if repo_url:
        extra = f"repo_url: {repo_url}\n"

    config = f"""site_name: {site_name}
{extra}theme:
  name: material
  features:
    - navigation.sections
    - navigation.expand
    - search.suggest
    - search.highlight
    - content.code.copy
  palette:
    - scheme: default
      primary: indigo
      accent: indigo
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    - scheme: slate
      primary: indigo
      accent: indigo
      toggle:
        icon: material/brightness-4
        name: Switch to light mode

plugins:
  - search

nav:
{_yaml_nav(nav)}
"""
    (work_dir / "mkdocs.yml").write_text(config, encoding="utf-8")


def _copy_docs(docs_dir: Path, work_dir: Path) -> None:
    """Copy the generated markdown docs into the working docs/ directory."""
    dest = work_dir / "docs"
    dest.mkdir()
    for filename, _ in NAV_ORDER:
        src = docs_dir / filename
        if src.is_file():
            shutil.copy2(src, dest / filename)
    # Add a generated index if readme.md is present, otherwise a placeholder.
    if (dest / "readme.md").is_file():
        shutil.copy2(dest / "readme.md", dest / "index.md")
    else:
        (dest / "index.md").write_text("# Documentation\n", encoding="utf-8")


def _run_mkdocs(work_dir: Path, out_dir: Path) -> None:
    """Run mkdocs build and copy the output into out_dir."""
    cmd = [
        sys.executable, "-m", "mkdocs", "build",
        "--config-file", str(work_dir / "mkdocs.yml"),
        "--site-dir", str(out_dir),
    ]
    proc = subprocess.run(cmd, cwd=str(work_dir), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"mkdocs build failed:\n{proc.stderr}\n{proc.stdout}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a static site from generated docs")
    parser.add_argument("--docs-dir", required=True, help="directory with the 14 generated markdown docs")
    parser.add_argument("--out-dir", required=True, help="output directory for the built site")
    parser.add_argument("--site-name", default="Repo Documentation", help="site title")
    parser.add_argument("--repo-url", default=None, help="optional repository URL for the site footer")
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir).resolve()
    out_dir = Path(args.out_dir).resolve()

    if not docs_dir.is_dir():
        print(f"error: docs-dir not found: {docs_dir}", file=sys.stderr)
        return 1

    work = Path(tempfile.mkdtemp(prefix="docs_site_"))
    try:
        _copy_docs(docs_dir, work)
        _write_mkdocs_config(work, docs_dir, args.site_name, args.repo_url)
        _run_mkdocs(work, out_dir)
        print(f"site built: {out_dir}")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
