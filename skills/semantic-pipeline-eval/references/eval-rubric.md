# Semantic evaluation rubric

One entry per judgment type in `semantic-pipeline-eval`'s Steps 2-4. Same structural intent as `skills/document-spring-repo/references/doc-taxonomy.md`: a single place stating exactly what counts as pass/fail, with worked examples, so two different runs of this skill classify the same evidence the same way.

---

## 1. Evidenced-claim truthfulness (Step 2)

For a sampled `[Evidenced — path:line]` claim, read the cited location ± a few lines of context and classify:

- **Supported** — the claim is a fair restatement of what the cited code actually shows.
- **Overstated** — the citation is real and on-topic, but the claim asserts more than the code actually establishes (e.g. citing a single `@PreAuthorize` annotation as evidence the *entire* controller is secured, when only one method carries it).
- **Contradicted** — the cited location says the opposite of, or is materially inconsistent with, the claim.
- **Citation irrelevant** — the citation resolves to a real file/line (so `test_pipeline_stages.py` passes it), but that location has nothing to do with the claim being made next to it.

**Worked true positive (Overstated):** claim reads `"All endpoints in InvoiceController require BILLING_READ [Evidenced — InvoiceController.java:11]"`, but line 11 is a `@PreAuthorize` annotation on exactly one of three methods in that controller. The citation is real; the claim's "All" isn't supported by it.

**Worked false positive to avoid:** claim reads `"This service persists invoices via JPA [Evidenced — Invoice.java:5]"`, line 5 is `@Entity`. Don't downgrade this to `Overstated` just because `@Entity` alone doesn't prove persistence *behavior* — the claim is about the mechanism (JPA-managed entity), which the annotation directly establishes. Overstated is for claims that outrun their citation's actual scope, not for claims making a reasonable inference from an annotation to what that annotation conventionally means.

---

## 2. Confirmed-tag hallucination (Step 1 mechanical pre-pass, Step 4 semantic confirmation)

`doc_engine.tools.semantic_eval_helpers.find_unmatched_confirmed_tags()` flags a `[Confirmed — interview, <date>]` tag when its preceding claim clause has low word-overlap with every "answered" entry in `interview_answers.json`. That's a worklist entry, not a verdict — confirm or reject each:

- **Confirmed hallucination** — no interview answer, close or otherwise, actually supports this claim. The tag is asserting an interview confirmation that didn't happen.
- **False positive — paraphrase, not hallucination** — a real interview answer does support the claim, just in different words than the mechanical overlap check could detect (e.g. the answer said "yes, that's the only writer" and the doc-writer rephrased it as "InvoiceService is the sole writer of this table" — real support, low literal word overlap).

**Worked true positive:** claim reads `"Deploy cadence is weekly [Confirmed — interview, 2026-07-23]"`, but `interview_answers.json` has no entry about deploy cadence at all, answered or skipped. Confirmed hallucination.

**Worked false positive to avoid:** claim reads `"InvoiceService is the sole writer of billing_invoice [Confirmed — interview, 2026-07-23]"`, and an entry exists with `topic: "write ownership: billing_invoice"`, `answer: "yes, that's correct, nothing else writes to it"`. Different wording, real support — reclassify as a false positive, not a hallucination.

---

## 3. Cross-doc / cross-diagram contradiction (Step 3)

Compare factual claims (component names, data-flow direction, entity/table names, security mechanism) across doc-writer files and against the merged architecture diagram:

- **Contradiction** — two sources make claims that cannot both be true (e.g. `database.md` lists `billing_invoice` as written only by `InvoiceService`, while `integrations.md` describes a different service writing to the same table with no caveat reconciling the two).
- **Not a contradiction** — two docs describing the same underlying fact from different angles or at different levels of detail. This is the more common case and the one worth guarding against over-flagging.

**Worked false positive to avoid:** `architecture.md` shows `InvoiceController --> InvoiceService --> InvoiceRepository`; `authorization.md` says `InvoiceController` requires `BILLING_READ`. These aren't in tension — one describes call flow, the other describes access control on the entry point. Don't flag differing *emphasis* as contradiction; only flag claims that are actually mutually exclusive.

---

## 4. Mermaid syntax (Step 1 mechanical pre-pass)

`check_mermaid_syntax()` is structural, not a full parser: bracket/paren/brace balance, `subgraph`/`end` balance, double-quote balance, and undefined node references (`find_undefined_node_refs()`). A finding here means the diagram is very likely malformed (truncated output, a mismatched quote from an entity name containing a stray `"`, a node whose label-bearing declaration got cut off), not that it necessarily fails to render — treat every finding as worth a quick look, not an automatic doc-writer re-run.

**On undefined node references specifically:** `adapters/claude/agents/architect-segment.md` rule 3 requires every real node to carry a genuine file/class label — never a bare, unlabeled identifier. `find_undefined_node_refs()` flags any identifier that shows up as an edge endpoint (`A --> Z`) but never receives a label (`Z["SomeFile.java"]`) anywhere else in the diagram. This is deliberately a different, narrower question than Step 2/`test_pipeline_stages.py`'s `find_untraceable_nodes()`: that one checks whether an *existing* label is a real file/class name (semantic traceability); this one only checks whether a node has *a* label at all (structural completeness). A node with a fabricated-but-present label (e.g. `"Billing Orchestration Service"`) is not flagged here — that's `find_untraceable_nodes()`'s job, not this one's.

**Worked true positive:** `A["InvoiceController.java"] --> Z` where `Z` never appears with a label anywhere else in the diagram — `Z` is flagged as an undefined node reference.

**Worked false positive to avoid:** `A["InvoiceController.java"] --> B` on one line, with `B["InvoiceService.java"] --> C[...]` later in the same diagram — `B` does get a real label eventually, just not on the line where it's first referenced. Not a finding.
