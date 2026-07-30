# Claim-symbol grammar (L3 normative)

**Status:** Normative for `FACTS_LEDGER_SCHEMA_VERSION = 2`  
**Implementation:** [`src/doc_engine/scanning/symbol.py`](../../src/doc_engine/scanning/symbol.py)  
**ADR:** [`claim-symbol-entity-identity-adr-2026-07-30.md`](claim-symbol-entity-identity-adr-2026-07-30.md)  
**Grammar version:** `SYMBOL_GRAMMAR_VERSION = 1` (independent of ledger schema version)

This file is the contract. Tests and emit code follow it. Do not invent alternate spellings in callers.

---

## 1. Wire form

```text
doc-engine spring . <path>
```

| Token | Value | Notes |
|-------|--------|------|
| scheme | `doc-engine` | Fixed |
| manager | `spring` | Fixed |
| package coord | `.` | Placeholder for name/version until real module coordinates exist — do not invent Maven GAV |
| path | see forms below | Namespace segments `/`-separated; type/member descriptors as below |

Prefix (including trailing space): `doc-engine spring . `

---

## 2. Forms

| Kind | Form | Example |
|------|------|---------|
| type | `<ns>/(<ns>/)*<Type>#` or `<Type>#` | `com/acme/billing/User#` |
| inner type | `…/<Outer>#<Inner>#` | `com/acme/Order#Line#` |
| field (reserved) | `…/<Type>#<field>.` | `com/acme/billing/User#email.` |
| method (reserved) | `…/<Type>#<method>().` | `com/acme/billing/User#getOrders().` |

**Missing Java `package` declaration:** no namespace segments → `doc-engine spring . User#`. Never invent a package from a file path.

**Inner classes:** use nested `#` descriptors (`Order#Line#`). Do **not** put Java binary `$` (`Order$Line`) in the symbol string. Mapping from source `$` / nested type decls to `#` is the extract layer’s job when member/inner emit exists; type-level L3 only needs the nested-`#` rule documented.

**Identifiers:** letter or `_` start; body letters, digits, `_`. No hyphens, spaces, or `/` inside a segment.

---

## 3. Golden examples (frozen — only place full-string equality is encouraged)

| Input | Symbol |
|-------|--------|
| package `com.acme.billing`, type `User` | `doc-engine spring . com/acme/billing/User#` |
| package `com.acme.auth`, type `User` | `doc-engine spring . com/acme/auth/User#` |
| no package, type `Order` | `doc-engine spring . Order#` |
| package `com.acme`, outer `Order`, inner `Line` | `doc-engine spring . com/acme/Order#Line#` |
| field `email` on billing `User` | `doc-engine spring . com/acme/billing/User#email.` |
| method `getOrders` on billing `User` | `doc-engine spring . com/acme/billing/User#getOrders().` |

Collision property: the two `User` rows above are **unequal** strings; both display as `User`.

---

## 4. Display vs machine

| Role | Where | Rule |
|------|--------|------|
| Machine identity | `MAPS_TO.subject` | Symbol string only; sole writers are `format_type` / later `format_field` / `format_method` |
| Human short name | `qualifiers.display_name` | Simple type name (e.g. `User`) — required on type maps |
| Java join aid | `qualifiers.fqcn` | Dotted FQCN (e.g. `com.acme.billing.User`) — required on type maps |
| Kind | `qualifiers.symbol_kind` | `type` for this PR |

`display(symbol)` derives human forms from the symbol (`User`, `User.email`, `User.getOrders()`). Prose docs should prefer `display_name` / FQCN, not raw symbols.

---

## 5. Illegal tokens (must reject)

Examples that `parse` must refuse: empty string; bare `User`; bare FQCN `com.acme.User`; missing trailing `#` on types; field missing trailing `.`; wrong scheme/manager; empty path after prefix.

`write_facts_jsonl` must refuse any `MAPS_TO` whose `subject` fails `parse` (write-time bite). Evidence subjects remain file paths and are not parsed as symbols.

---

## 6. API surface

| Function | Role |
|----------|------|
| `format_type(package, type_name, *, inner=())` | Type symbols (production emit) |
| `format_field` / `format_method` | Reserved; tested; not emitted until member facts exist |
| `parse(symbol)` | Structured parts; raises `SymbolError` |
| `display(symbol)` | Human form from symbol |
| `fqcn_of(package, type_name, *, inner=())` | Qualifier helper |

No ad-hoc string concatenation of subjects outside this module.

---

## 7. Versioning

- Bumping **grammar** (breaking symbol spellings) → bump `SYMBOL_GRAMMAR_VERSION` and regenerate affected fixtures.
- Bumping **ledger** field meaning (v1 simple-name → v2 symbol) → bump `FACTS_LEDGER_SCHEMA_VERSION` (already 2). Facts are scan-regenerated; no dual-read of simple-name + symbol subjects.
- Path A `entity_table_map` stays simple-name-keyed until a separate identity slice.

---

## 8. Non-goals

SCIP/Glean/Kythe wire; member fact rows in this PR; Path A rekey; inventing package-manager coordinates.
