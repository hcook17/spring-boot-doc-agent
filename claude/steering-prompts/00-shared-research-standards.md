# Shared research standards for the steering prompts

This file is referenced by the five category prompts (`01`–`05`) in `claude/steering-prompts/`, and by the review layer (`10`–`12`) as its research counterpart — `10-review-persona-and-standards.md` governs *review and judgement* and states only its delta from this file. Read it first, once, before running any of them — it defines the bar every finding in every category must clear, so results are comparable across categories and consistent with this project's existing research (`claude/spring-boot-doc-agent-review.md`, `claude/comparable-tools-benchmark.md`, `claude/sdd-brownfield-research-2026-07.md` — these live in the Claude project "Plugin For Asynchronous Documentation Creation," not in this repo; ask the user for access or a copy if you need the full text).

## Why the five category prompts exist

A principal-engineer review of `spring-boot-doc-agent` (this plugin) is largely done and its launch-blocking bugs are fixed — see `IMPLEMENTATION_HANDOFF.md` and this repo's own history for the technical detail. What's still missing isn't more bug fixes to the pipeline logic; it's scaffolding *around* the pipeline that makes it trustworthy to operate: automated testing of the LLM stages (not just the two deterministic scripts), formal contracts between stages, a single place that states what this tool does and doesn't do, and run-level telemetry so a human doesn't have to read fourteen markdown files to know if a run went well. Each of the five prompts (`01` through `05`) scopes one of these gaps into its own research → scaffold → implement task.

## Research methodology (apply in every category)

**arXiv.** Search for papers specifically on-topic for the category — keyword overlap with the abstract is not the bar; the mechanism described has to actually apply to what you're building. Before citing any paper, confirm it resolves at `arxiv.org/abs/<id>` and actually says what you're about to claim it says. This project has already verified two real, on-point papers this way (ArchAgent, arXiv:2601.13007, for the partitioning algorithm; FActScore, arXiv:2305.14251, for claim-tagging precedent) — match that bar.

**GitHub repos**, filtered by two independent signals, neither sufficient alone:
- *Star count* is a triage filter, not a quality verdict. A rough floor around 300–500 stars for a tooling-category repo screens out abandoned toy projects, but don't discard a smaller, precisely on-point repo without actually checking it.
- *Recency of pushes* — check the repo's actual commit activity, not just stars. A high-star repo with no push in 2+ years is a legacy snapshot, not current practice; note this explicitly if you use it anyway.
- When both signals are weak or absent, say so plainly rather than presenting the finding with unearned confidence.

**DeepWiki cross-check.** For every GitHub repo that becomes a serious candidate, check whether it's indexed at `https://deepwiki.com/<org>/<repo>`. If it is, read the generated wiki *before* diving into raw source. DeepWiki's per-claim citations are commit-and-line-pinned and have held up under spot-checking in this project's prior research — but its own generation pipeline is closed-source and unverified, so treat DeepWiki's prose as a fast orientation layer, and re-verify any specific claim against the actual linked source line before citing it as fact.

**Tagging findings.** Every claim gets marked confirmed-via-primary-source-you-actually-opened, versus plausible-but-unverified. Don't blur the two.

## What "scaffold and implement" means here

Research alone isn't the deliverable. Each prompt ends with a concrete artifact to actually build inside this plugin — a schema file, a test harness, a markdown doc, a manifest emitter — sized to be genuinely useful without requiring new infrastructure or dependencies beyond what the plugin already assumes (Python stdlib, `ast-grep` on PATH, no new services). If research surfaces a heavier solution than needed, say so and scope down rather than importing complexity for its own sake.

## Mirrored copy — keep in sync

**Only `00` through `06` are mirrored** from the Claude project's `claude/steering-prompts/` docs, so a local Claude Code CLI session (which has no access to that project) can read them directly. Those six have a canonical copy there; **`07` through `12` do not** — they were authored in this repo and exist nowhere else. Confirmed 2026-07-24: the project's `steering-prompts/` folder holds `00`–`06` and nothing further.

So the sync obligation is one-directional and narrow: **if you edit `00`–`06` here, the canonical copy in the Claude project needs the same edit made back** — note it in your commit message or in `claude/session-log.md` so a project-connected session picks it up. Editing `07`–`12` creates no such obligation; there is nothing to sync them with unless someone deliberately adds them to the project.

**Direction, settled by content comparison on 2026-07-24.** All seven prompts were *authored in the project first* and copied into this repo afterwards — so the "mirrored from the project" framing describes the original import correctly. What has never happened is the return leg: since the import, every edit has been made here, and not one has been mirrored back. The project is the origin; the repo is the working copy of record.

Two things that a commit count alone would have gotten wrong, both checked by diffing the project copies against every historical revision of their repo counterparts:

- **`00`, `01` and `05` were rewritten by the import commit itself** (`8bb2404`), not by later drift — condensed, and re-worded from "in this project" to "in this repo". Their project copies have never matched any revision that existed here. They are two revisions behind, not one.
- **`02` is not stale at all.** Its project copy is byte-identical to the current repo file, despite a post-import commit touching it (`c65d89e` restored the same content). `06` matches too, modulo a missing final newline on the repo side. A manifest that infers "diverged" from "has commits since import" overstates the backlog by two files.

**Nobody has edited the project copies since they were created**, so there is no fork: every project copy is either an exact ancestor of the repo file or the pre-import original the import rewrote. Mirroring repo → project is a safe overwrite, not a merge. If that ever stops being true, say so here, because then the two have genuinely forked and the overwrite becomes wrong.

*(This paragraph previously claimed `01` through `12` were all mirrored from the project. That was wrong — it was widened from the original, correct `01`–`05` during a docs sweep without checking what the project actually contains, which is the exact "prose winning over reality" failure this repo's own tooling exists to catch. Corrected here.)*
