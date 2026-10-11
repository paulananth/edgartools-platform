# 07c Unstructured extraction

Type: task. Phase: B. Blocked by: 07; the cross-checks also wait for Codex's Rust join port. Map: [map](../map.md). Plan: [plan](../plan.md).

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
- [ ] HTML and iXBRL deterministic + cross-checked
  - [ ] iXBRL first: a reading contract on one captured filing's inline XBRL; record whether the engine reads it unchanged, and any primitive it lacks (a GoF consult and an operator ruling before any engine change)
  - [ ] HTML tables and labelled sections: a Python custom step, or an engine primitive once a second source needs it
- [ ] PDF (Python custom step)
- [ ] Free text (Python custom step)
- [ ] Unconfirmed candidates keep their location, never merge (cross-checks as configuration; waits for Codex's Rust join port)
