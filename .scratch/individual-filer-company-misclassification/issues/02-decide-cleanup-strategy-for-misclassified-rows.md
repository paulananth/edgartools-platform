Type: grilling
Status: claimed
Blocked by: 01

## Question

Should the ~32,948 already-misclassified `sec_company`/`mdm_company` rows
(individuals wrongly typed as companies) be cleaned up, and if so, how --
delete, reclassify, or quarantine-and-flag? Should this wait on the
discovery-time prevention fix, or proceed independently?

## Answer

Grilled with the operator; four decisions locked:

1. **End state:** yes, these ~33K individuals should eventually be tracked
   correctly as persons, with real IS_INSIDER/HOLDS relationships derived
   for them -- not just removed from the company universe and forgotten.
   Confirmed live (this ticket's investigation): none of the 3 sampled
   individuals (Zuckerberg, Huang, Olivan) have any `mdm_person` row at
   all, and only 104 of 19,462 person-shaped `mdm_company` rows overall
   have a matching `mdm_person` by CIK -- so for ~99.5% of this
   population, no correct identity exists anywhere in MDM today. This
   isn't a duplicate-cleanup problem; it's closer to "these people were
   never actually resolved as persons."
2. **Timing:** cleanup waits for the discovery-time root-cause fix (still
   fog -- see map's "Not yet specified") to ship first. Cleaning up now,
   before the upstream CIK-discovery gap is closed, would just get
   recreated by the next `daily_incremental` run.
3. **Mechanism:** delete outright -- remove the bad `sec_company`/
   `mdm_company`/`mdm_entity` rows (and their derived COMPANY_HOLDS
   relationship rows) entirely, relying on the underlying raw
   ownership-filing data (`sec_ownership_reporting_owner`/
   `sec_ownership_non_derivative_txn`/`sec_ownership_derivative_txn`,
   untouched by this bug) plus the *fixed* resolver to correctly
   re-derive each individual as a proper `mdm_person` with real
   IS_INSIDER/HOLDS relationships on a subsequent run. Rejected
   quarantine-flag-only (doesn't actually get them out of company-count
   views' underlying rows, just hides them) and in-place reclassification
   (real migration risk moving `entity_id` references across
   `mdm_relationship_instance`/`mdm_source_ref`/`mdm_change_log` for no
   real benefit when the correct entity doesn't exist yet anyway to merge
   into).
4. **Rollout:** piloted -- verify the delete mechanism against a small,
   already-investigated sample (the 3 CIKs from Ticket 01) first, confirm
   the fixed pipeline correctly re-resolves them as persons with real
   relationships, before running at the full ~33K scale. Matches this
   session's established dry-run-first convention for every other
   prod-mutating action.

**Next in sequence, not yet ticketed:** the discovery-time root-cause fix
itself (the map's first "Not yet specified" item -- exact CIK-discovery
call site still needs tracing) blocks this cleanup from proceeding at
all. That's the next decision to graduate into a ticket, not this one.
