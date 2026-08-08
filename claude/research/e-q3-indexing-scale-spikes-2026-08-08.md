# E-Q3 / S3 indexing & scale spikes (research only — no build yet)

## S3-1 Materialized Stage-0 index
**Question:** SQLite/Parquet/mmap vs full JSON scan?
**Refs:** DDIA Ch.3/10; agentmako SQLite index
**Exit:** ADR after measuring OCS dependents+evidence scan latency. Default until then: full scan.

## S3-2 Packet-as-row_ref + lazy expansion
**Status:** Partially landed in Option A emission (`row_ref`). Remaining: expandableTools MCP follow-up.
**Refs:** agentmako context tools

## S3-3 Ranking
Keep lexical overlap; hold BM25/hybrid as eval spike with fixed bucket baselines.
**Refs:** DRACO arXiv:2405.19782

## S3-4 Official MCP Python SDK
Upgrade thin stdio shell later; keep `dispatch_tool` as SoR.
**Refs:** modelcontextprotocol/python-sdk DeepWiki

## S3-5 FreshnessPolicy parity
`prefer_fresh` / `require_fresh` / `allow_stale` knobs — after AssumeIndexed→unknown honesty.
**Refs:** agentmako freshness docs

## S3-6 Sandbox
Only if tools leave read-only — see S-STF-F.
**Refs:** arXiv:2601.01241
