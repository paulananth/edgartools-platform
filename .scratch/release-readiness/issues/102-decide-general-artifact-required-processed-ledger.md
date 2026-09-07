# 102 — Decide whether to generalize the required/processed artifact ledger beyond filing-text

Type: grilling
Status: open
Blocked by: 101

## Question

Ticket 101's trigger-condition resolution designed a narrow, filing-text-
specific `required`/`processed` sweep (folded into `daily_incremental`).
While resolving it, two other places in this codebase turned out to
already track the same *shape* of state independently:

1. `artifact_required` (`edgar_warehouse/application/relationship_bulk_load.py`)
   feeding `daily_artifact_resume.py`'s "immutable manifest, outcome
   ledger, candidate-only resume" (release-readiness Ticket 63) — scoped
   to whether ownership/13F/ADV artifacts are needed for relationship-
   derivation candidates.
2. The binary-attachment cleanup need (Tickets 70/71) — same "captured but
   not actually needed, should be a cleanup candidate" shape, one artifact
   type over (images/exhibits rather than text).

Should this be unified into one general-purpose artifact ledger (required/
processed/cleanup-candidate, parameterized by artifact type), or should
each artifact type keep its own narrow, independently-designed tracking
the way Ticket 101 just did for text? Ticket 101 deliberately deferred
this rather than deciding it inline, to avoid scope creep on a
already-well-scoped sub-question.

## Considerations to weigh (not yet decided)

- **For unifying:** one ledger, one mental model, one place to look for
  "what's safe to delete across the whole bronze/silver estate" — matters
  more as more artifact types accumulate their own ad hoc tracking (this
  is now the third instance of the same shape).
- **Against unifying:** each artifact type's `required` definition is
  genuinely different (Ticket 101's is CIK-scoped and ticker/recency-
  gated; `artifact_required`'s is relationship-candidate-scoped; binary-
  attachment's is per-document-type). A shared schema forcing these into
  one shape risks the same "one field conflates two distinct concerns"
  failure this repo's CLAUDE.md already documents for
  `EXCLUDED_OPERATIONAL_TABLES` — worth reading that 5-whys entry before
  designing a shared table.
- **Timing:** Ticket 101's sweep hasn't even been implemented yet: there is
  no live evidence yet of how well the narrow, type-specific design works
  in practice. Deciding to generalize before that exists risks designing
  the shared abstraction around a guess rather than a proven pattern.

## Answer

(not yet resolved)
