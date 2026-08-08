# Docs honesty — query surface (E-Q4)

## Claims that must match probes

| Claim | Status after E-Q0 |
|---|---|
| MCP cannot read outside server root | True — `require_server_root` + no caller `root` |
| `tokensUsed` bounds serialized emission | True — Option A `row_ref` + full JSON chars/4 |
| Unknown filters fail closed | True — evidence bucket / facts predicate errors |
| Freshness without repo is `unknown` | True — `AssumeIndexed.freshness_for` |
| Nested fan-out capped | True — `truncate_nested_lists_that_exceed_cap` in registry |

## Agent prompt rule

Orchestrators must pass run_dir under `DOC_ENGINE_ROOT`. Never invent absolute paths for MCP tool args.

## CI lane wording

OCS real-artifact tests remain an **optional local lane** when artifacts are present; they are not a substitute for hermetic unit/property suites.
