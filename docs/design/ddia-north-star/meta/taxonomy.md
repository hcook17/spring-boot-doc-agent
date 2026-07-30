---
id: taxonomy
kind: taxonomy
completeness: operational
tags: [epub, taxonomy, ncx, sect, leaf]
related: []
path: meta/taxonomy.md
last_refined: 2026-07-30
---

# Epub taxonomy (DDIA 2e package model)

Measured against a local 2e epub (not in git). Use this when attaching new notes to the right structural slot.

## Package schema

| Layer | Role | Observed shape |
|-------|------|----------------|
| `META-INF/container.xml` | Rootfile pointer | → `OEBPS/content.opf` |
| OPF manifest | Asset SoR | ~148 items (HTML, PNG, fonts, CSS, JS, NCX) |
| OPF spine | Linear reading order | cover → front matter → ch01–14 → back matter |
| `toc.ncx` | Nav derived tree | **477** `navPoint`s; depths **0–3**; all `src` use `#fragment` |

Package SoR = OPF + chapter HTML. NCX/HTML TOC are **indexes** (secondary access), same pattern as repo coverage: fixtures/rules = SoR; STATUS/CI comments = indexes.

## Sectioning (DocBook-like)

Chapter HTML uses CSS section classes more than a pure HTML5 outline:

| Class | Approx count (ch01–14) | Role |
|-------|------------------------|------|
| `div.chapter` | 14 | Chapter root |
| `div.sect1` | 63 | Major sections |
| `div.sect2` | 153 | Subsections (≈ NCX depth 2) |
| `div.sect3` | 237 | Sub-subsections (≈ NCX depth 3) |

## Heading vocabulary (typed leaves)

| Level | Role |
|-------|------|
| H1–H3 | Outline / sect titles |
| H4 | **Unused** |
| H5 | **Examples** + per-chapter **Footnotes/References** |
| H6 | **Notes** (many titled `Note`) + **figure captions** |

Do not treat H5/H6 as outline depth — they are leaf content kinds.

## Content model under sections

Dominant: `<p>`, `<em>`, `<code>`, `<a>`. Also: `<dl>/<dt>/<dd>` (definitional — e.g. SoR vs derived), `<figure>`/`<img>`, `<aside class="sidebar">`, lists, rare `<table>`/`<pre>`.

**Ignore:** `koboSpan` / reader chrome classes — noise for indexing.

## NCX ↔ HTML

Almost all NCX labels align to H1–H3 titles. Unmatched labels are front/back matter (Preface, Glossary, book title).

## Indexing recipe for enrichments

Attach new paraphrases under:

`(chapter, sect path or fragment id, leaf kind, concept tags)`

Never commit raw HTML blobs from the epub.
