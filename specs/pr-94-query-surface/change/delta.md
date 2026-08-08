# Change delta (OpenSpec-style)

## ADDED Requirements

- C1: Arbitrary file read: containment opt-in; nothing opts in
- C2: `tokensUsed` under-reports; budget does not bound serialized output

## MODIFIED Requirements

- H1: Nested fan-out unbounded; `truncated` lies
- H2: `RedactionProvider` dead on production shape
- H3: Unknown filters → silent empty success
- H4: MCP fault isolation missing

## REMOVED Requirements

- Caller-supplied MCP root
- AssumeIndexed as default freshness lie
