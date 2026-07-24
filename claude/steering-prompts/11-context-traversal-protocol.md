# 11 — Context traversal protocol (DFS/BFS over the evidence graph)

An executable procedure for building understanding of an unfamiliar region — a subsystem, a
dependency, a body of research — without unbounded reading. Pairs with
`10-review-persona-and-standards.md` (tiers and verdicts) and `00-shared-research-standards.md`.

This formalises the project instruction *"search for docs in repository that show you index of
repos and investigate them; if a file links to another, discern if it's useful and continue to
follow it."* The addition is bounds and a stopping rule.

---

## 1. The graph

**Nodes** are artifacts that can carry a claim: a repo file, a GitHub repo root, a Javadoc page, a
spec document, an arXiv paper, an issue thread, a `.proto`/schema file, a migration guide, a
deepwiki page.

**Edges** are anything that points from one artifact to another: an explicit hyperlink, a
`see-also`, an import, a citation, a superseded-by note, a named identifier you can search for, a
"this replaces X" line.

**Node metadata** you must record for every visited node: canonical identifier (URL or repo-relative
path), evidence tier (§2 of file 10), and whether it is *claim-bearing* — does it assert something
that could change a conclusion, or is it navigation only? Index pages, tables of contents, and most
deepwiki pages are navigation, not claims. This distinction drives the stopping rule.

**Visited set** keyed on canonical identifier. Cycles are common (docs cross-link freely); without
this you will loop.

---

## 2. DFS — targeted descent to ground one claim

Use when you have a *specific* proposition that needs Tier A grounding.

```
dfs(claim, node, depth):
  if depth > MAX_DEPTH:            return UNRESOLVED(frontier = outbound(node))
  if tier(node) == A and node answers claim:
                                   return CONFIRMED(path)
  for child in outbound(node) ordered by likelihood of being Tier A:
      if child in visited:         continue
      result = dfs(claim, child, depth+1)
      if result != DEAD_END:       return result
  return DEAD_END
```

Rules:

- **Never terminate on a Tier C node.** If the current node is Tier C, it is a pointer, not an
  answer. Either it has an outbound edge toward a Tier A candidate, or this branch is a dead end.
- **The path is the citation.** Record the full chain, not just the endpoint. A chain that passes
  through Tier C requires the terminal Tier A node to be read directly.
- **`MAX_DEPTH = 5`** unless the task says otherwise. Exhausting it returns UNRESOLVED *with the
  frontier attached* — never silently, and never as REFUTED.
- **Order children by expected tier.** A link to a Javadoc or a source file outranks a link to a
  blog post. This is the whole reason DFS is the right shape here: you are trying to reach an
  authority quickly, not to enumerate.

---

## 3. BFS — ring expansion to map a region

Use when you have a *region* to understand and do not yet know which nodes matter.

```
bfs(seeds, concept_set):
  frontier = seeds; ring = 0
  while ring < MAX_RINGS:
      scored = [(score(n, concept_set), n) for n in expand(frontier) if n not in visited]
      keep   = top RING_WIDTH nodes with score >= THRESHOLD
      log(dropped = len(scored) - len(keep))        # never silent
      visit(keep); frontier = keep; ring += 1
```

`score(node, concept_set)` — rank on, in descending weight:

1. **Contradiction potential.** Does this node plausibly *disagree* with something already held?
   Weight this highest; disconfirming evidence is worth more than more confirming evidence.
2. **Invariant relevance.** Does it bear on an arity, a constraint, a termination argument, a
   compatibility guarantee?
3. **Term overlap** with the concept set (identifiers, annotation names, predicate names).
4. **Authority** — a Tier A node outranks a Tier C node at equal relevance.

Defaults: `MAX_RINGS = 3`, `RING_WIDTH = 7`. **Log every drop.** A dropped node is a bound you
applied, and per file 10 §4 an unstated bound reads as completeness.

---

## 4. The interleave

BFS and DFS are not alternatives; they compose.

> **BFS to discover, DFS to ground.**

One iteration:

1. BFS one ring from the current frontier. Cheap reads only — titles, abstracts, headings, file
   names. Do not read bodies yet.
2. Every node scoring above threshold that is *claim-bearing* becomes a DFS seed.
3. DFS each seed to Tier A. Emit CONFIRMED / REFUTED / UNRESOLVED per claim.
4. Feed newly discovered identifiers back into `concept_set` — this is what makes the next ring
   smarter than the last.
5. Repeat.

The concept-set feedback in step 4 is the part that makes this converge rather than wander. If a
ring adds no new terms to the concept set, that is a strong saturation signal.

---

## 5. Stopping rule — "done" requires two independent signals

Do not stop on one. Require **at least two** of:

- **S1 — Saturation.** Two consecutive BFS rings produce zero new claim-bearing nodes. (Navigation
  nodes do not count; an index page full of links you have already visited is not new information.)
- **S2 — Closure.** Every open claim is either Tier A grounded or explicitly marked UNRESOLVED with
  a stated reason and its frontier.
- **S3 — Consistency.** No two retained claims contradict each other without a recorded `contested`
  verdict naming both sources.
- **S4 — Diminishing return.** The last ring changed no verdict and no recommendation.

**Budget exhaustion is not a stopping signal.** Hitting `MAX_RINGS`, a hop cap, or a time limit
means the traversal was **truncated**, not **done**. Those must be reported with different words and
the open frontier must be written out. Conflating them is the exact failure mode this repo already
ships in its drift report, where a summary listing only `unchanged` reads as "docs are current."

---

## 6. deepwiki.com

Use `deepwiki.com/<owner>/<repo>` to orient on an unfamiliar repository: to find out which files
matter, what the module boundaries are, and what a subsystem is called. That is a legitimate and
efficient BFS accelerator — it collapses a ring of blind directory listing into one read.

Then **leave**. Read the actual files in the actual repository and cite those. deepwiki is Tier C:
it is a generated summary, it can be stale relative to the repo's default branch, and it can be
confidently wrong about details. It has already been used correctly on this project once — for SCIP
orientation, re-verified against `scip.proto` — and that is the pattern to repeat, not vary.

Same treatment for arXiv: the abstract and the related-work section are excellent BFS fuel; a claim
sourced from a paper must come from the paper's own body, and a claim about *software* sourced from
a paper is Tier B at best.

---

## 7. Bookkeeping and resumption

Maintain, and write to disk before the session ends:

- **`visited`** — canonical id, tier, claim-bearing yes/no, one-line what-it-said.
- **`frontier`** — unexpanded nodes with their scores, so the next session resumes mid-traversal
  instead of restarting from seeds.
- **`claims`** — claim, verdict, tier, source path, version checked against, date.
- **`contradictions`** — any pair that forced a `contested`.
- **`bounds applied`** — every drop, cap, and skip, with counts.

The next session reads these files. It does not read this session's transcript, and it does not
re-derive the traversal. That is the whole point.
