"""One-shot: deepen chapters, fix frontmatter paths, rebuild catalog.json."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD = Path(__file__).resolve().parents[3] / "claude" / "research" / "ddia-north-star"

CHAPTERS = {
    1: {
        "title": "Trade-Offs in Data Systems Architecture",
        "thesis": "Architecture is tradeoffs among operational vs analytical needs, SoR vs derived data, and distribution costs — not free upgrades.",
        "sections": [
            "Operational Versus Analytical Systems",
            "Systems of Record and Derived Data",
            "Cloud Versus Self-Hosting",
            "Distributed Versus Single-Node Systems",
            "Data Systems, Law, and Society",
        ],
        "claims": [
            "Operational vs analytical workloads differ in access patterns and latency expectations.",
            "SoR holds each fact once; derived data is recomputable; on discrepancy SoR wins by definition.",
            "Cloud and distribution are tradeoffs (ops burden, failure modes, cost), not default wins.",
            "Legal/societal constraints can dominate technical elegance — document them as first-class.",
        ],
        "related": [
            "sor-vs-derived",
            "batch-vs-stream-derived-state",
            "maintainability-operability-evolvability",
            "domain-data-flow-and-truth",
        ],
        "domains": ["01-data-flow-and-truth", "05-maintainability-and-change"],
        "who": "Architects, principals, and anyone choosing homes for facts vs views in this product or a target Spring system.",
        "what": "The vocabulary for SoR vs derived, operational vs analytical, and when distribution is worth the cost.",
        "when": "Before new artifact homes, dual writers, or “just cache it” decisions; at ADR and PR design review.",
        "where": "Pipeline facts vs certification; rules vs coverage baselines; STATUS vs code; customer DB vs read models.",
        "why": "Without this chapter’s distinctions, teams invent second SoRs and call them caches.",
        "how": "Name writer and readers; prefer recompute over LWW; cite `sor-vs-derived` / `rel-sor-feeds-views`; file deviations when departing.",
        "questions": [
            "What is the single writer for this fact?",
            "Is this artifact recomputable? From what?",
            "Are we paying distribution cost for a real need?",
        ],
        "completeness": "operational",
    },
    2: {
        "title": "Data Models and Query Languages",
        "thesis": "The data model shapes what is easy to express, evolve, and query — document and relational tradeoffs are real.",
        "sections": [
            "Relational Model Versus Document Model",
            "Many-to-One and Many-to-Many Relationships",
            "Data Query Languages",
            "Graph-Like Data Models",
        ],
        "claims": [
            "Document vs relational is about locality and join cost, not fashion.",
            "Many-to-many usually needs an explicit relationship representation.",
            "Query language choice constrains evolvability and access patterns.",
            "Graph models fit highly connected domains; do not force them elsewhere.",
        ],
        "related": ["encoding-and-compatibility", "domain-encoding-and-evolution"],
        "domains": ["02-encoding-and-evolution"],
        "who": "Anyone designing schemas for target Spring apps or for this repo’s JSON/artifact models.",
        "what": "How entities and relationships are represented and queried.",
        "when": "New entity types, join-heavy features, or choosing document blobs vs normalized tables.",
        "where": "Customer JPA/entities; this repo’s catalog.json, facts, baselines.",
        "why": "Wrong model creates permanent accidental complexity (`maintainability-operability-evolvability`).",
        "how": "Map access patterns first; encode relationships explicitly; evolve with schema discipline (ch05).",
        "questions": [
            "What are the primary access patterns?",
            "Where are many-to-many edges represented?",
            "What breaks if we denormalize for read speed?",
        ],
        "completeness": "partial",
    },
    3: {
        "title": "Storage and Retrieval",
        "thesis": "Storage engines trade write path, read path, and compaction — indexes are derived data with a cost.",
        "sections": [
            "Data Structures That Power Databases",
            "Transaction Processing or Analytics?",
            "Column-Oriented Storage",
        ],
        "claims": [
            "Indexes and column stores are derived structures optimized for reads.",
            "OLTP vs OLAP storage choices follow access patterns from ch01.",
            "Compaction and write amplification are operational costs of derived indexes.",
        ],
        "related": ["materialized-views-and-caches", "sor-vs-derived"],
        "domains": ["01-data-flow-and-truth"],
        "who": "Engineers choosing indexes, caches, or analytical stores.",
        "what": "How on-disk structures serve queries.",
        "when": "Performance work, new indexes, analytical pipelines.",
        "where": "Target DB indexes; this repo’s materialized views (certification, baselines).",
        "why": "Treating an index/cache as SoR recreates dual-writer bugs.",
        "how": "Treat indexes/views as derived; measure rebuild cost; cite `materialized-views-and-caches`.",
        "questions": [
            "Is this structure rebuildable from SoR?",
            "What is the write amplification?",
        ],
        "completeness": "partial",
    },
    4: {
        "title": "Encoding Formats and Modes of Dataflow (bridge into ch05)",
        "thesis": "How data moves (DB, RPC, async messages) constrains encoding and evolution options.",
        "sections": [
            "Formats for Encoding Data (preview)",
            "Modes of Dataflow (preview)",
        ],
        "claims": [
            "In-memory objects ≠ durable encodings.",
            "DB dump, RPC, and event logs have different compatibility windows.",
            "Prefer explicit schemas for multi-language and long-lived data.",
        ],
        "related": ["encoding-and-compatibility", "schema-evolution-and-data-outlives-code"],
        "domains": ["02-encoding-and-evolution"],
        "who": "API and pipeline authors.",
        "what": "Encoding formats and dataflow modes at a survey level (deepen via ch05).",
        "when": "New RPC/event/artifact formats.",
        "where": "REST/JSON, facts.jsonl, certification, baselines.",
        "why": "Silent format drift breaks readers across deploys.",
        "how": "Open ch05 concepts; use `rel-schema-outlives-writers`.",
        "questions": ["Which dataflow mode is this?", "Who still reads the old encoding?"],
        "completeness": "partial",
    },
    5: {
        "title": "Encoding and Evolution",
        "thesis": "Encodings must evolve because data outlives code; compatibility is a schema discipline under skew.",
        "sections": ["Formats for Encoding Data", "Modes of Dataflow"],
        "claims": [
            "Data outlives code; old encodings remain until migrated.",
            "Compatibility: prefer additive fields with defaults under skew.",
            "Schemas help multi-language evolution and tooling.",
            "DB vs RPC vs event dataflow have different evolution constraints.",
        ],
        "related": [
            "schema-evolution-and-data-outlives-code",
            "encoding-and-compatibility",
            "rel-schema-outlives-writers",
            "dev-fp-ratchet-separate-from-recall",
        ],
        "domains": ["02-encoding-and-evolution"],
        "who": "Anyone changing baselines, JSON schemas, Pydantic models, or fixture formats.",
        "what": "Forward/backward compatibility, schema evolution, dataflow modes.",
        "when": "Any additive or breaking change to on-disk or over-wire shapes.",
        "where": "catalog.schema.json, semgrep FP baseline, certification shapes, check_repo_claims predicates.",
        "why": "Inventing fake SoR numbers to satisfy a new field is a band-aid (`dev-fp-ratchet-separate-from-recall`).",
        "how": "Additive first; version bumps with migration; separate ratchets when failure directions invert.",
        "questions": [
            "Can old readers accept new writers?",
            "Did we invent a baseline without measurement?",
        ],
        "completeness": "operational",
    },
    6: {
        "title": "Replication",
        "thesis": "Replication buys durability and scale at the cost of lag and conflict — lag is not optional magic.",
        "sections": [
            "Leaders and Followers",
            "Problems with Replication Lag",
            "Multi-Leader Replication",
            "Leaderless Replication",
        ],
        "claims": [
            "Follower lag means readers can see stale state.",
            "Multi-leader and leaderless designs create conflict classes you must name.",
            "LWW is a conflict strategy with data loss risk — not a default.",
        ],
        "related": ["replication-lag-and-lww", "rel-conflict-vs-recompute"],
        "domains": ["03-replication-and-conflicts"],
        "who": "Reviewers of dual homes, multi-writer docs, or “eventual” views.",
        "what": "How copies stay (or fail to stay) consistent.",
        "when": "Any second writer or async view of the same fact.",
        "where": "STATUS vs queue; certification vs facts; mirrored docs under claude/ vs docs/design.",
        "why": "Silent LWW of prose and code created the coverage blindspot.",
        "how": "Prefer single writer + recompute; cite `rel-conflict-vs-recompute`; file deviations for true multi-writer.",
        "questions": ["Which replica is allowed to accept writes?", "What happens on concurrent updates?"],
        "completeness": "operational",
    },
    7: {
        "title": "Partitioning",
        "thesis": "Partitioning scales by splitting data — skew and cross-partition operations become first-class costs.",
        "sections": [
            "Partitioning and Replication",
            "Partitioning of Key-Value Data",
            "Partitioning and Secondary Indexes",
            "Rebalancing Partitions",
        ],
        "claims": [
            "Partition key choice dominates hot spots.",
            "Secondary indexes and cross-partition queries reintroduce coordination cost.",
            "Rebalancing is an operational event, not free.",
        ],
        "related": ["maintainability-operability-evolvability", "batch-vs-stream-derived-state"],
        "domains": ["05-maintainability-and-change", "01-data-flow-and-truth"],
        "who": "Engineers sharding work (e.g. Stage-4 fan-out, group partitions).",
        "what": "How work and data are split across nodes/groups.",
        "when": "Capacity and fan-out designs (adoption L2).",
        "where": "partition_repo, capacity_preflight, group edges.",
        "why": "Wrong partition key creates permanent hotspots and band-aid caches.",
        "how": "Name partition key and skew plan before coding; avoid silent rebalance assumptions.",
        "questions": ["What is the partition key?", "What queries cross partitions?"],
        "completeness": "partial",
    },
    8: {
        "title": "Transactions",
        "thesis": "Transactions protect integrity under concurrency — know which anomalies you still allow.",
        "sections": [
            "The Meaning of ACID",
            "Weak Isolation Levels",
            "Serializability",
        ],
        "claims": [
            "ACID words are overloaded; name the anomaly you prevent.",
            "Weak isolation is common and lossy under concurrent RMW.",
            "Serializability is expensive — use when correctness requires it.",
        ],
        "related": ["transactions-and-integrity-lite", "trust-but-verify-and-auditability"],
        "domains": ["04-integrity-and-verification"],
        "who": "Authors of concurrent updates to shared artifacts or DB rows.",
        "what": "Isolation and integrity under concurrency.",
        "when": "RMW on baselines, shared STATUS edits, concurrent pipeline writers.",
        "where": "DB transactions in target apps; file locks / single-writer conventions here.",
        "why": "Lost updates look like “random CI flakes.”",
        "how": "Single writer or explicit transaction; cite lite concept; don’t pretend soft merges are serializable.",
        "questions": ["What anomaly is possible?", "Who serializes writers?"],
        "completeness": "partial",
    },
    9: {
        "title": "The Trouble with Distributed Systems / Consistency and Consensus (lite atlas)",
        "thesis": "Partial failure is normal; consistency and consensus are tools with costs — most of this product should avoid needing them.",
        "sections": [
            "Faults and Partial Failures",
            "Unreliable Networks",
            "Consistency Guarantees (survey)",
            "Consensus (survey)",
        ],
        "claims": [
            "Timeouts are guesses; networks lie.",
            "Strong consistency needs coordination cost.",
            "Prefer designs that need less consensus (single SoR writer).",
        ],
        "related": ["consistency-and-consensus-lite", "domain-consistency-and-coordination"],
        "domains": ["06-consistency-and-coordination"],
        "who": "Anyone proposing distributed locking or multi-primary truth for this product.",
        "what": "Failure modes and consistency vocabulary (lite).",
        "when": "Before introducing cross-node coordination.",
        "where": "Rare in this monorepo meta path; more relevant in target distributed Spring systems.",
        "why": "Consensus theater is a common band-aid for unfixed single-writer design.",
        "how": "Default to domain 01 solutions; deepen this domain before relying on it (`partial`).",
        "questions": ["Can a single writer remove the need for consensus?", "What partial failure looks like here?"],
        "completeness": "partial",
    },
    10: {
        "title": "Batch Processing (bridge)",
        "thesis": "Batch derives large views offline; immutable inputs enable safe reprocessing.",
        "sections": ["Batch themes preview — see ch11"],
        "claims": [
            "Batch fits bulk transforms with lagged freshness.",
            "Immutable inputs enable replay.",
        ],
        "related": ["batch-vs-stream-derived-state", "ch11"],
        "domains": ["01-data-flow-and-truth"],
        "who": "Authors of offline derivation jobs.",
        "what": "Batch as derivation (full treatment in ch11).",
        "when": "Large recomputes, ETL-like doc/artifact builds.",
        "where": "Coverage corpus scans, report generation, Stage-0 batch tools.",
        "why": "Confusing batch outputs with SoR creates dual writers.",
        "how": "Open ch11 + `batch-vs-stream-derived-state`.",
        "questions": ["Can we replay from immutable inputs?"],
        "completeness": "partial",
    },
    11: {
        "title": "Batch Processing",
        "thesis": "Batch processing derives large views offline; treat outputs as serving-layer loads, not live SoR writes.",
        "sections": [
            "Batch Processing with Unix Tools",
            "Batch Processing in Distributed Systems",
            "Batch Processing Models",
            "Batch Use Cases",
        ],
        "claims": [
            "Batch fits bulk transforms with lagged freshness.",
            "ETL is derivation from operational SoR to analytical/serving views.",
            "Serve derived data via stage+load, not live row writes from batch into SoR.",
            "Immutable inputs enable safe reprocessing.",
        ],
        "related": [
            "batch-vs-stream-derived-state",
            "materialized-views-and-caches",
            "sor-vs-derived",
            "rel-sor-feeds-views",
        ],
        "domains": ["01-data-flow-and-truth"],
        "who": "CI authors, Stage-0 tool authors, anyone regenerating large derived artifacts.",
        "what": "Offline derivation patterns and serving-layer loads.",
        "when": "Rebuilding coverage results, catalogs, certification, docs sites.",
        "where": "`_build_catalog.py`, coverage scripts, `build_docs_site`, pipeline batch stages.",
        "why": "Writing batch outputs back into SoR without a clear writer creates the certification/LWW class of bugs.",
        "how": "Inputs immutable or versioned; outputs regenerated; cite `rel-sor-feeds-views`.",
        "questions": [
            "What is the input SoR snapshot?",
            "Can we delete outputs and rebuild?",
        ],
        "completeness": "operational",
    },
    12: {
        "title": "Stream Processing",
        "thesis": "Streams derive continuous views with fresher latency — still derived, still need SoR discipline.",
        "sections": [
            "Transmitting Event Streams",
            "Databases and Streams",
            "Processing Streams",
        ],
        "claims": [
            "Streams are derived timelines, not automatic SoR.",
            "Fresher views still conflict with SoR on discrepancy.",
            "Exactly-once and ordering are hard; name the guarantee you actually have.",
        ],
        "related": ["batch-vs-stream-derived-state", "sor-vs-derived"],
        "domains": ["01-data-flow-and-truth"],
        "who": "Authors of incremental/watch-mode pipelines.",
        "what": "Continuous derivation vs batch.",
        "when": "Choosing streaming freshness over batch cost.",
        "where": "Future incremental doc pipelines; target Kafka/stream apps.",
        "why": "“Real-time” does not authorize dual writers.",
        "how": "Compare freshness need vs batch; keep SoR clear; cite `batch-vs-stream-derived-state`.",
        "questions": ["What latency do we need?", "What ordering/delivery guarantee do we actually have?"],
        "completeness": "operational",
    },
    13: {
        "title": "The Future of Data Systems (themes)",
        "thesis": "Unbundling, derived data, and reasoning about correctness remain the long-term design pressure.",
        "sections": [
            "Data Integration",
            "Unbundling Databases",
            "Correctness and Reasoning",
        ],
        "claims": [
            "Systems unbundle into SoR + specialized derived serving layers.",
            "Integration is about honest dataflow, not more LWW.",
            "Correctness needs explicit reasoning and auditability.",
        ],
        "related": [
            "maintainability-operability-evolvability",
            "trust-but-verify-and-auditability",
            "sor-vs-derived",
        ],
        "domains": ["05-maintainability-and-change", "01-data-flow-and-truth", "04-integrity-and-verification"],
        "who": "Principals setting multi-year direction for doc-engine.",
        "what": "Where the industry pressure points land for this product.",
        "when": "Roadmaps, major refactors, unbundling decisions (kernel vs adapters).",
        "where": "`docs/product-architecture.md`, kernel vs meta split, north-star itself.",
        "why": "Without a north star, unbundling becomes random file moves (the old `claude/` concentration problem).",
        "how": "Keep design SoR under `docs/design/`; cite domains; refuse band-aid dual homes.",
        "questions": ["Are we unbundling SoR from views cleanly?", "What correctness property is audited?"],
        "completeness": "operational",
    },
    14: {
        "title": "Building Reliable, Scalable, and Maintainable Applications (closing themes)",
        "thesis": "Reliability, scalability, and maintainability are explicit goals — operability and evolvability are how you keep them.",
        "sections": [
            "Reliability",
            "Scalability",
            "Maintainability",
        ],
        "claims": [
            "Reliability is continuing to work correctly under faults.",
            "Scalability is coping with growth — measure load parameters.",
            "Maintainability splits operability, simplicity, evolvability.",
        ],
        "related": ["maintainability-operability-evolvability", "refactor-sequencing", "architecture-decision-review"],
        "domains": ["05-maintainability-and-change"],
        "who": "Every engineer on this project at review time.",
        "what": "The three pillars and how they show up in gates and design.",
        "when": "PR review, capacity work, complexity debates.",
        "where": "CI gates, capacity_preflight, agent/tool constraints, docs/design.",
        "why": "Features that ignore operability become adoption blockers.",
        "how": "Use playbooks `architecture-decision-review` and `refactor-sequencing`; cite maintainability concept.",
        "questions": [
            "What fault did we design for?",
            "What is the load parameter?",
            "Did we add accidental complexity?",
        ],
        "completeness": "operational",
    },
}


def render_chapter(num: int, meta: dict) -> str:
    cid = f"ch{num:02d}"
    sections = "\n".join(f"- {s}" for s in meta["sections"])
    claims = "\n".join(f"- {c}" for c in meta["claims"])
    related = ", ".join(meta["related"])
    linked = "\n".join(f"- {r}" for r in meta["related"] if not r.startswith("domain-") and r != f"ch{num:02d}")
    domains = "\n".join(f"- `{d}`" for d in meta["domains"])
    questions = "\n".join(f"- {q}" for q in meta["questions"])
    return f"""---
id: {cid}
kind: chapter
completeness: {meta["completeness"]}
tags: [chapter, {cid}]
related: [{related}]
path: chapters/{cid}.md
last_refined: 2026-07-30
---

# Chapter {num}. {meta["title"]}

## One-sentence thesis

{meta["thesis"]}

## Who this chapter is for

{meta["who"]}

## What it covers

{meta["what"]}

## When to apply

{meta["when"]}

## Where it shows up in systems

{meta["where"]}

## Why it matters

{meta["why"]}

## How to use it here

{meta["how"]}

## Section map

{sections}

## Digested claims

{claims}

## Linked concept ids

{linked}

## Linked domains

{domains}

## Principal questions

{questions}

## Completeness / gaps

Marked `{meta["completeness"]}`. Do not treat outline/partial chapters as sole ADR authority.

## Epub file

OEBPS/ch{num:02d}.html (local Tier A; not vendored in git)
"""


def fix_path(path: Path, rel: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return
    end = text.find("\n---", 3)
    block = text[3:end]
    body = text[end + 4 :]
    if re.search(r"^path:", block, re.M):
        block = re.sub(r"^path:.*$", f"path: {rel}", block, count=1, flags=re.M)
    else:
        block = block.rstrip() + f"\npath: {rel}\n"
    path.write_text("---" + block + "\n---" + body, encoding="utf-8")


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
    # always trust filesystem path
    data["path"] = path.relative_to(ROOT).as_posix()
    return data


def main() -> None:
    # chapters
    ch_dir = ROOT / "chapters"
    ch_dir.mkdir(exist_ok=True)
    for num, meta in CHAPTERS.items():
        path = ch_dir / f"ch{num:02d}.md"
        path.write_text(render_chapter(num, meta), encoding="utf-8")

    # taxonomy path
    tax = ROOT / "meta" / "taxonomy.md"
    if tax.is_file():
        text = tax.read_text(encoding="utf-8")
        if not text.startswith("---"):
            # old taxonomy may have path: taxonomy.md
            pass
        fix_path(tax, "meta/taxonomy.md")
        # ensure kind taxonomy
        t = tax.read_text(encoding="utf-8")
        if "kind: taxonomy" not in t.split("---", 2)[1]:
            pass

    # fix concept/relationship/domain/deviation/playbook paths
    for path in ROOT.rglob("*.md"):
        rel = path.relative_to(ROOT).as_posix()
        if path.name in {"README.md", "INDEX.md", "COMPLETENESS.md", "_TEMPLATE.md"}:
            continue
        if path.parent == ROOT:
            continue
        if path.name == "README.md" and "domains" in rel:
            # domain README has frontmatter
            fix_path(path, rel)
            continue
        if any(
            p in rel
            for p in (
                "concepts/",
                "relationships/",
                "playbooks/",
                "chapters/",
                "deviations/dev-",
                "meta/taxonomy",
            )
        ):
            fix_path(path, rel)

    # collect catalog entries
    entries = []
    entries.append(parse_frontmatter(ROOT / "meta" / "taxonomy.md"))
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

    # filter related that may not resolve yet — keep as-is; test will catch
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
    print(f"wrote {len(entries)} entries to {ROOT / 'catalog.json'}")


if __name__ == "__main__":
    main()
