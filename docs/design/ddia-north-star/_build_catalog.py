"""Build catalog.json from docs/design/ddia-north-star page frontmatter."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"missing frontmatter: {path}")
    end = text.find("\n---", 3)
    block = text[3:end]
    data: dict = {
        "tags": [],
        "related": [],
        "epub_anchors": [],
        "path": path.relative_to(ROOT).as_posix(),
    }
    for line in block.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("id:"):
            data["id"] = s.split(":", 1)[1].strip()
        elif s.startswith("kind:"):
            data["kind"] = s.split(":", 1)[1].strip()
        elif s.startswith("completeness:"):
            data["completeness"] = s.split(":", 1)[1].strip()
        elif s.startswith("last_refined:"):
            data["last_refined"] = s.split(":", 1)[1].strip()
        elif s.startswith("tags:"):
            inner = s.split(":", 1)[1].strip().strip("[]")
            data["tags"] = [t.strip() for t in inner.split(",") if t.strip()]
        elif s.startswith("related:"):
            inner = s.split(":", 1)[1].strip().strip("[]")
            data["related"] = [t.strip() for t in inner.split(",") if t.strip()]
        elif s.startswith("- {"):
            ch = re.search(r"chapter:\s*(\d+)", s)
            fr = re.search(r"fragment:\s*([^,}]+)", s)
            ti = re.search(r'title:\s*"([^"]+)"', s)
            if ch and ti:
                anchor = {"chapter": int(ch.group(1)), "title": ti.group(1)}
                if fr:
                    frag = fr.group(1).strip().strip(",")
                    if frag:
                        anchor["fragment"] = frag
                data["epub_anchors"].append(anchor)
    if not data.get("epub_anchors"):
        data.pop("epub_anchors", None)
    for key in ("id", "kind", "completeness", "last_refined"):
        if key not in data:
            raise ValueError(f"{path} missing {key}")
    data["path"] = path.relative_to(ROOT).as_posix()
    return data


def main() -> None:
    entries = [parse_frontmatter(ROOT / "meta" / "taxonomy.md")]
    for path in sorted((ROOT / "domains").glob("*/README.md")):
        entries.append(parse_frontmatter(path))
    for path in sorted(ROOT.glob("domains/*/concepts/*.md")):
        entries.append(parse_frontmatter(path))
    for path in sorted(ROOT.glob("domains/*/relationships/*.md")):
        entries.append(parse_frontmatter(path))
    for path in sorted((ROOT / "playbooks").glob("*.md")):
        entries.append(parse_frontmatter(path))
    for path in sorted((ROOT / "chapters").glob("*.md")):
        entries.append(parse_frontmatter(path))
    for path in sorted((ROOT / "deviations").glob("dev-*.md")):
        entries.append(parse_frontmatter(path))
    payload = {
        "schema_version": 1,
        "last_refined": "2026-07-30",
        "$comment": (
            "Machine index for docs/design/ddia-north-star. Bodies live in markdown; "
            "keep 1:1 by id. Sync test enforces."
        ),
        "entries": entries,
    }
    (ROOT / "catalog.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(entries)} entries")


if __name__ == "__main__":
    main()
