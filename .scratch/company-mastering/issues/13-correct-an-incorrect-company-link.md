# Correct an incorrect Company link

Type: task
Status: done, merged #748 (2026-09-29)
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
3. **Never the same wrong link again.** A rule never proposes a record again
   under the version a revocation named, to any Company: keyed by record,
   rule and version, so a later merge of the Company cannot bring it back.
4. **Rerun, bounded.** `stale_bindings`: the binds whose rule version is no
   longer switched on. A correction batch revokes them; in the same
   transaction the active rules re-propose those records, so each binds
   again under an approved version, to the same or another Company, or waits.
5. **Quarantine** (built 2026-09-29): a `quarantine` decision in the journal
   names the record and the Company it was linked to. The record must be
   unbound first (its bind revoked, in the same batch or before); while it is
   held no rule proposes it and replay refuses any bind of it; the Company
   carries `quarantined: true` (the dated row's column, 037). A `revoke` of
   the quarantine lifts it, and the lifted record is reconsidered by the
   rules in the same batch.

   Two readings of the 09:31 ruling, written down for the operator:
   - **Which Company is flagged.** The ruling says each quarantined record
     "stays its own Company with a `quarantined` flag". A GLEIF record never
     owns a Company here (operator, 2026-09-24: an unlinked GLEIF record
     waits), so the flag goes on the Company it was linked to: readers see
     that Company has a link no rule could decide. The SEC record keeps its
     own Company. **Operator, 2026-09-29 10:06 ET: yes.**
   - **What lifts it.** "Only an operator-approved rule change": a lifting
     revocation must name a policy other than the one the quarantine was
     made under (`correction.check_lifts`); the same policy is refused. The
     quarantine and the lift each name the policy of the batch that carries
     them, which the Merge Stage runs only once registered.
   - The Stage row stays, unbound; the journal decision is its mark.
     **Operator, 2026-09-29 10:07 ET: yes.**

## The operator's command

`edgar-warehouse mdm correction-batch --policy-digest … --actor … --reason …
--at … [--limit N] [--quarantine SUBJECT]… [--lift SUBJECT]… --output FILE`
writes one correction batch's decisions (`correction.correction_batch`): it
revokes every standing link a rule version no longer switched on made, and
any link of a record named for quarantine; quarantines those records; lifts
the named quarantines. They run as a stewardship batch through
`apply-decisions`.

## Review (2026-09-29, three axes)

- Spec: a stored quarantined record was still paired by name matching when
  its SEC record came again (fixed: filtered in `matching.propose`, PG16
  test); the lift check now ties both policies to the batch's own; the
  operator had no command (added above); the relink guard missed a merged
  Company (now keyed without it).
- Standards: the quarantine lookup is bounded to the batch's records; the
  released records are computed once per batch; `stale_bindings` filters
  and limits in SQL; revocations are built in one query; 041 refuses unless
  exactly one operation check exists.
- GoF: leave the structure.

## Checklist

- [x] Preserve the old decision, its source and bronze-object references, policy
  version, and the correction decision in the journal. The bind stays; the
  revocation carries its target, subject, Company, rule and version,
  evidence, the Stage row's bronze object and the policy in force.
- [x] Prove split and quarantine on PostgreSQL 16 with dated Company rows, aliases,
  field provenance, duplicate delivery, and publication retry
  (`tests/integration/test_clean_binding_correction.py`, 14 tests): dated
  rows close and open on revoke, quarantine and lift; GLEIF's values and
  their provenance leave the Company; a correction delivered twice changes
  nothing; a quarantine publishes through a lost acknowledgement; a later SEC
  batch never pairs with a quarantined record; the correction command's
  batch quarantines and lifts; migration 041 on a populated store. Aliases: a merge's reversal was already proven
  (`test_merge_alias_reversal_preserves_later_evidence_and_exclusion`); a
  bind makes no alias.
- [x] Reassessment is bounded (`stale_bindings`' limit), idempotent (a
  rerun finds nothing; a redelivered batch is a duplicate), and blocks a
  stale or conflicting link (the same rule version never relinks the pair;
  a bind is revoked once only; a revocation names the bind it revokes).
- [x] Do not switch on the declared name matching rules until this is implemented
  and separately approved. None is on; ticket 20 brings their approval.
