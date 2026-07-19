# 21 — Insider-scoped EMPLOYED_BY completeness (Release Owner scope decision, 2026-07-19)

Type: task
Status: open
Blocked by: none
Blocks: 20 (relaunch of the strict bulk-load execution)

## Release Owner decisions (2026-07-19, given verbatim intent: "form 4/5 should
## be tied to 5.02 identification; anyone who has an insider must be identified;
## everyone else is not needed; 13F and other forms are not critical")

1. **13F stays in the freeze but is non-blocking**: keep loading all 101,444
   13F candidates; do not spend launch-gating effort auditing 13F paths;
   fix-forward on 13F issues. (The 13F NULL-period bug is already fixed —
   PR #192.)
2. **EMPLOYED_BY identification is scoped to insiders**: the required
   person-identification universe = people who appear in Form 3/4/5 insider
   filings (already parsed by edgar_warehouse/parsers/ownership.py; MDM
   already derives IS_INSIDER). Item 5.02/proxy events need resolution only
   when the person is an insider; unresolved events for non-insiders are
   not-needed rather than accepted-gap.

## What to build

A revised completeness evaluation for the Ticket 20 gate: instead of "every
Item 5.02 candidate reaches terminal resolution," prove "every insider
(Form 3/4/5 filer) for every in-scope CIK is identified in MDM," with Item
5.02/proxy loaded best-effort under the existing bounded unresolved_accepted
gate. Requires cross-referencing ownership filings against the employment
identification set at evidence time, and revising
docs/release-readiness/required-relationship-bulk-load-completion-gate.md
"Done when" accordingly BEFORE the next strict execution fires.

Note: this reframes (and likely shrinks) the unresolved-Item-5.02 problem —
an ambiguous 8-K only matters if the undisclosed person is an insider, and
insiders are independently identifiable from their own Form 3/4/5 filings.

## Current deployed state (ready, holding)

- Task def `edgartools-prod-medium:29` = warehouse image
  `@sha256:163cfc3b…` (`sha-c2bcd97996cf`): parser v5 + bounded
  unresolved_accepted gate (0.095) + 13F cover-period fix. Smoke-tested.
  SM `edgartools-prod-bronze-seed-silver-gold` references `:29`.
- Freeze `ticket20-agent-20260718T225510Z` (fingerprint `abecbde8…`)
  unchanged, preflight READY_FOR_STRICT_LOAD, execution input on S3.
- Consumed execution names (P3, never reuse): ticket20-strict-agent-20260718T225510Z,
  ticket20-strict-gatev2-20260719T135202Z, plus all earlier ticket20-strict-*.
- Launch requires: this ticket's doctrine revision, then a brand-new
  execution name, then the Release Owner's explicit go.

**Status:** ready-for-agent

- [ ] Spec the insider-scoped completeness check (cross-reference design:
      ownership filings ↔ MDM person identification ↔ Item 5.02 events)
- [ ] Revise the completion-gate doctrine's "Done when" + PASS claim
- [ ] Implement the evidence-time insider-coverage check
- [ ] Relaunch the strict execution (new name, explicit user go)
