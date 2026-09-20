# Write the mastering policy language specification and hand it to Codex

Type: task
Status: resolved
Blocked by: none (06 resolved 2026-09-20)

## Question

The destination. Write `docs/specs/mdm/policy-language.md` from this
map's resolved tickets: the document model (per kind, composed into one
pinned body), the three rule families, the primitive vocabulary and its
versioning, activation per `(rule_id, rule_version, verdict)` with its
proof block and the Merge Stage predicate, survivorship and projection,
authoring and validation, change and replay. Carry the two prototypes as
worked examples.

State every dependency on Clean MDM honestly, including the open items
this map raised for Codex: the composite-digest provenance churn
(research 01) and the one-sided 95% vs 97.5% confidence mismatch in
accepted Q11 (research 02). Then write the handover note under
`.scratch/handover/` pointing a Codex session at the spec.

Planning only: no code, no migration, no edit to any Clean MDM file.

## Answer

Resolved 2026-09-20. Written:

- [`docs/specs/mdm/policy-language.md`](../../../docs/specs/mdm/policy-language.md)
  — sixteen sections: purpose, scope, terms, document model, the twelve
  primitives and versioning, the three rule shapes, the Identifier
  Contract, activation (`measured` and `deterministic`, with the Merge
  Stage predicate and the defer-and-count runtime), the eight registration
  checks, change and replay, worked examples, six items for Codex, six
  release gates, five Open items, and the evidence table.
- [`.scratch/handover/2026-09-20-claude-to-codex-mastering-policy-language.md`](../../handover/2026-09-20-claude-to-codex-mastering-policy-language.md)
  — the pointer note.
- `CONTEXT.md` — **Mastering Policy** and **Identifier Contract** added to
  the glossary.

Not verified: the spec has not had a documentation review against the map
and repository (the foundation spec's gate 4 pattern). Recorded as the
next step on the map, not claimed done.
