# Correct an incorrect Company link

Type: task
Status: in progress (Claude, branch `claude/company-mastering-13-correct-a-link`)
Blocked by: 09, 10
Blocks: activation of the SEC-to-GLEIF name matching rules

## Outcome

An operator can identify an incorrect SEC-to-GLEIF binding, correct the rule,
and rerun the Merge Stage on current Stage evidence. The old combined Company
version closes, the original surviving and aliased immutable IDs are restored
to their rightful Companies, and the wrong pair cannot relink under the same
rule. If no qualified rule can decide the split, quarantine the records without
dropping evidence or allowing automatic matching.

## Rulings this builds on (ticket 10, operator 2026-09-24)

- 09:29 ET: a wrong merge is a rule defect: **fix the rules**; the rule gets
  a new, tested version and the merge re-runs on the current Stage rows,
  which splits the wrong Company. If the rules cannot fix it, **quarantine**.
- 09:31 ET: quarantined records stay in the Stage, marked, are left out of
  matching, each stays its own Company with a `quarantined` flag readers
  see; only an operator-approved rule change lifts it.

## Found (2026-09-29 06:05 ET, Claude)

- A wrong SEC-to-GLEIF link is a **bind** (the GLEIF record joined to the
  Company its SEC record holds), not a merge. The engine reverses a merge
  (`reverse`), but a bind can never move: `identity.replay` and the Stage
  (`record_binding`, migration 039) both refuse it. That refusal names
  "a correction contract": this ticket.
- Only `bind` comes from an automatic rule (`binding.py`, `matching.py`); a
  merge is always a Steward's decision, and its reversal and aliases already
  work (`test_merge_alias_reversal_preserves_later_evidence_and_exclusion`).
- Ticket 10's slice 2a (the Stage's `entity_id`) is the one dependency; it is
  merged. Slices 2b to 4 (the Merge Stage reading the Stage, compact
  receipts, stopping the growth) do not block a correction: it is a decision
  in the journal, replayed like any other. 2b's end-of-batch routing of a
  contradiction stays in ticket 10.

## Design (Claude, from the rulings)

1. **Revoke a bind.** `revoke` may target a `bind`: the subject is unbound.
   A later bind of that subject, to any Company, must come at or after the
   revocation. The revocation is the receipt: the bind it revokes, its
   subject and Company, the rule and version that made it, its evidence, the
   Stage row's bronze object, the policy in force, and why.
2. **The Stage follows.** Migration 041: a revocation clears the Stage row's
   `entity_id` in the same transaction, before the batch's binds, so the
   record can bind again.
3. **Never the same wrong link again.** A rule never proposes a pair a
   revocation named, under the version it named.
4. **Rerun, bounded.** `stale_bindings`: the binds whose rule version is no
   longer switched on. A correction batch revokes them; in the same
   transaction the active rules re-propose those records, so each binds
   again under an approved version, to the same or another Company, or waits.
5. **Quarantine** (its own slice): an operator decision in the journal; the
   records are left out of matching, their Companies flagged; only a
   revocation lifts it.

## Checklist

- [ ] Preserve the old decision, its source and bronze-object references, policy
  version, and the correction decision in the journal.
- [ ] Prove split and quarantine on PostgreSQL 16 with dated Company rows, aliases,
  field provenance, duplicate delivery, and publication retry.
- [ ] Reassessment is bounded, idempotent, and blocks a stale or conflicting link.
- [ ] Do not switch on the declared name matching rules until this is implemented
  and separately approved.
