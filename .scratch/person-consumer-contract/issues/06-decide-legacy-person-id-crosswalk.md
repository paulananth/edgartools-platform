# Decide how legacy Person IDs and silver back-propagated IDs map to mdm_v2

Type: grilling
Status: open
Blocked by: 02-decide-what-binds-a-person.md

## Question

Legacy `mdm_entity` rows with `entity_type = 'person'` have IDs that were
back-propagated into silver (`sec_ownership_reporting_owner.mdm_entity_id`,
`sec_adv_filing.mdm_entity_id`). Clean MDM says legacy IDs become "an
explicitly verified, versioned crosswalk," not carried IDs. For Person:
is the crosswalk built from `owner_cik`/CRD equality only (deterministic),
are legacy fuzzy-matched persons re-adjudicated or dropped, and what does
the silver back-propagation column mean after cutover (rewritten, frozen
as legacy, or dropped)?
