# 07c Unstructured extraction

Priority: 31, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/profiling/issues/07c-unstructured-extraction.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task. Status: resolved (2026-11-03 18:43 ET, closed with every part moved or deferred). Phase: B. Blocked by: 07; the cross-checks also wait for Codex's Rust join port. Map: [map](../../profiling/map.md). Plan: [plan](../../profiling/plan.md).

## Where each part runs (Rust or Python)

Asked by the operator, 2026-10-11: "should 07c be done in rust?" Recorded on
the operator's request ("write that into the 07c ticket", 2026-10-11 17:46 ET)
as the recommendation, then approved as the ruling (operator, 2026-10-11 17:52 ET: "approve
the 07c table").

The rule is Codex's responsibility map (`docs/architecture/runtime-responsibilities.md`,
`codex/responsibility-map`): generic configured computation runs in Rust through
Python callers; anything one source needs alone is a Python custom step.

| Part | Where | Why |
|---|---|---|
| iXBRL tags | Rust, as configuration | Inline XBRL must be well-formed XHTML, so it is XML, which the engine already reads (`quick-xml`). Reading tagged facts (name, context, unit, scale, sign) is the same for every filer. Possibly no engine change: try a contract on one filing first. |
| HTML tables and labelled sections | Rust only if generic | Real HTML is not XML: the engine would need an HTML parser and a declared table or section primitive. Built only when two or more sources need it; until then a Python custom step. |
| PDF | Python custom step | Text out of a PDF depends on each publisher's layout; Python's PDF libraries are far ahead of Rust's. |
| Free text | Python custom step | Patterns are publisher-specific; plan decision 27 accepts nothing unless cross-checked, so most stays "candidate, unconfirmed". |
| Cross-checks; unconfirmed never merges | Configuration (Rust) | Comparing an extracted value with structured data is a combine and quality check: Codex's Rust join port and the MDM quality checks. |

Recommendation: no "Rust rewrite" for 07c. Start with iXBRL (the largest gain,
probably configuration only); add an HTML primitive to the engine only when a
second source needs it; PDF and free text stay Python custom steps behind the
cross-check gate.

## Checklist

- [x] The operator rules on where each part runs (the table above): approved, "approve the 07c table" 2026-10-11 17:52 ET
- [ ] ~~HTML and iXBRL deterministic + cross-checked~~ deferred: the HTML part is built under ticket 149 (`read.format: html`, S-1 and F-1); iXBRL waits for a source whose captured filings carry inline XBRL tags
  - [ ] ~~iXBRL first~~ deferred: no source needs it yet (2026-11-03 18:43 ET); open a ticket for the source that does
  - [ ] ~~HTML tables and labelled sections~~ moved to ticket 149 (its second source justifies the engine primitive)
- [ ] ~~PDF (Python custom step)~~ deferred: no source needs it yet; SEC main documents are HTML or text
- [ ] ~~Free text (Python custom step)~~ moved to ticket 149 for S-1 and F-1 offering terms; other free text deferred until a source needs it
- [ ] ~~Unconfirmed candidates keep their location, never merge~~ deferred: nothing extracts unconfirmed values yet; it waits for Codex's Rust join port
