# Correct an incorrect Company link

Type: task
Status: open
Blocked by: 09 and 10
Blocks: activation of the SEC-to-GLEIF name matching rules

## Outcome

An operator can identify an incorrect SEC-to-GLEIF binding, correct the rule,
and rerun the Merge Stage on current Stage evidence. The old combined Company
version closes, the original surviving and aliased immutable IDs are restored
to their rightful Companies, and the wrong pair cannot relink under the same
rule. If no qualified rule can decide the split, quarantine the records without
dropping evidence or allowing automatic matching.

## Acceptance

- Preserve the old decision, its source and bronze-object references, policy
  version, and the correction decision in the journal.
- Prove split and quarantine on PostgreSQL 16 with dated Company rows, aliases,
  field provenance, duplicate delivery, and publication retry.
- Reassessment is bounded, idempotent, and blocks a stale or conflicting link.
- Do not switch on the declared name matching rules until this is implemented
  and separately approved.
