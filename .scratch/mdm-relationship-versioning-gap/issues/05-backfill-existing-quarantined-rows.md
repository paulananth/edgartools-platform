Type: task
Status: open

Blocked by: 01, 02, 03

## Question

Decide and implement how the ~199,252 already-quarantined
`mdm_relationship_instance` rows in prod get corrected, now that Tickets
01-03 have landed the real fix for all 5 affected types. A targeted SQL
correction pass (walk each affected `relationship_id`, re-apply the
corrected close/supersede logic retroactively against existing rows) vs. a
full re-derivation (`derive-relationships` rerun for all 5 types against
already-captured silver data) are the two candidate shapes -- not decided
yet, deliberately blocked until the corrected logic exists (backfilling
under the still-buggy logic would just re-quarantine the same rows, as
Ticket 01's own traced example already shows happening for fresh writes
today).

## Answer

(not yet resolved)
