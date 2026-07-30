# How to use the north star at every level

This catalog is intentionally **multi-resolution**. Same vocabulary; different depth depending on the job.

## Levels

### 1. Product / direction

**Ask:** What kind of system are we building, and which DDIA tradeoffs do we refuse?

**Open:** [README.md](../README.md) scope table → domain README that owns the concern → any matching [deviation](../deviations/).

**Output:** Directional constraint in STATUS / ADR / PR description citing concept `id`s.

### 2. Domain

**Ask:** Which cluster of concerns am I in (truth, encoding, replication, integrity, maintainability, consistency)?

**Open:** `domains/NN-*/README.md`.

**Output:** Domain map of concepts + relationships; do not invent a new vocabulary for that cluster.

### 3. Subdomain (concept)

**Ask:** What is the precise claim set for this decision?

**Open:** one `concepts/*.md` page. Required sections (In one sentence … Anti-patterns) are the contract.

**Output:** Decision or review finding citing the `id`.

### 4. Relationship

**Ask:** How do two artifacts / concepts interact? Who writes? Who derives? Who wins on conflict?

**Open:** `domains/*/relationships/*.md` or a playbook that encodes the relationship.

**Output:** Explicit edge: writer → reader, SoR → view, fact → ratchet. If the edge is “merge two writers,” stop and open `replication-lag-and-lww` + deviations.

### 5. Control / gate / schema

**Ask:** What concrete mechanism enforces the claim?

**Open:** playbooks (`coverage-gates`, `claims-and-status-drift`, …) + the concept that justifies them.

**Output:** Code + baseline + CI wiring; catalog `id` in the PR body.

### 6. Upstream / downstream diagnosis

**Ask:** Is this local pain caused by a bad upstream design (dual writer, wrong SoR, silent LWW, band-aid cache)?

**Procedure:**

1. Name the symptom artifact.
2. Trace **upstream writers** and **downstream consumers**.
3. Check whether a [deviation](../deviations/) already justifies the shape.
4. If not: either fix the upstream SoR/relationship, or file a deviation with evidence — **never** ship an undocumented workaround.

## Who / what / when / where / why / how (default questions)

Use these on every chapter and every non-trivial decision:

| Lens | Question |
|------|----------|
| **Who** | Who writes? Who reads? Who is accountable when they disagree? |
| **What** | What fact or artifact is in scope? What is explicitly out of scope? |
| **When** | When does the rule apply (design time, CI, runtime, incident)? |
| **Where** | Where in the repo / pipeline / target system does this live? |
| **Why** | Why this tradeoff rather than the obvious alternative? |
| **How** | How do we enforce, observe, and reverse the choice? |

Chapters under [chapters/](../chapters/) answer these explicitly. Concepts answer them in compressed form; relationships and deviations must not leave them implicit.

## Anti-band-aid rule

A fix is a **band-aid** if it:

- leaves two writers for one fact, or
- teaches a derived view to “win” over SoR without a filed deviation, or
- papers a schema/docs drift with a one-off comment instead of fixing SoR or the derivation, or
- adds complexity that only makes sense if an upstream design error remains untouched.

Prefer: fix SoR → fix relationship → document intentional deviation with evidence → (last) temporary mitigation with an expiry and owner.
