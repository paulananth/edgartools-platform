# Write the mastering policy language specification and hand it to Codex

Type: task
Status: open
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
