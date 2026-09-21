# Decide how legacy Person IDs and silver back-propagated IDs map to mdm_v2

Type: grilling
Status: resolved 2026-09-20
Blocked by: 02-decide-what-binds-a-person.md

## Answer

**No crosswalk. Legacy Person IDs are dropped, not mapped.** The operator
asked the right question — "why do we still need legacy person id, did we
not cover all using the new research and updated MDM?" — and the evidence
agrees. This ticket was charted before the Snowflake directive and the
legacy decommission, and those two facts removed its consumers.

**Who still holds a legacy Person id** (verified 2026-09-20):

| Holder | State |
| --- | --- |
| `mdm_person` / `mdm_entity` in legacy MDM Postgres | legacy MDM is being decommissioned (operator, 2026-09-19) |
| Silver `mdm_entity_id` columns | Snowflake `EDGARTOOLS_SILVER` — will not be restored |
| Graph person nodes | Snowflake `NEO4J_GRAPH_MIGRATION` — same |
| **Gold** | **never used them**: no gold model references a person `mdm_entity_id`, there is no person dimension, and `ownership_holdings` keys owners on a hash of `'cik:' \|\| owner_cik` else `'name:' \|\| owner_name_norm` (`ownership_holdings.sql:63-67`) |
| MDM API `/persons/*` | undeployed |

So the crosswalk's consumers are one store being decommissioned, two that
no longer exist, and a gold layer that never used the ids. Clean MDM
already prescribes the alternative: "rebuild from approved pinned source
assertions, not from presumed-clean legacy master rows"
(`domain-model.md:84-89`), which is what ticket 20's principle requires
anyway.

**The ids are also not worth preserving on their merits.** The legacy
fuzzy path's context check can never pass, so any name score ≥ 0.92 was
clipped to `REVIEW` — and in ordinary mastering `REVIEW` **binds**
(`resolvers/base.py:268-288`). A CIK-less reporting owner attached to any
existing person scoring Jaro-Winkler ≥ 0.80 across the whole table, with
no human gate, under a normalizer built for company names. Carrying those
ids forward would import silent over-merges into a contract whose point
is measured precision.

**The one thing that carries: human judgment, as evidence, not as an id.**
Resolved `mdm_match_review` rows and `_merge_entities` tombstones are
curated Steward decisions. If legacy MDM Postgres is still reachable they
are harvested as **source assertions** ("a Steward said these two records
are the same person") to be re-adjudicated under the current rules; if it
is unreachable, or the table is empty — likely, since `MdmMatchReview`
rows are queued only under `reconciliation_mode=True` (`base.py:263-266`)
— nothing is lost. Either way no legacy id is carried.

**Silver's `mdm_entity_id`** is frozen as legacy: never read, never
rewritten by Clean MDM. Dropping the columns is the silver owner's call
([ticket 22](22-decommission-legacy-person-code-and-tests.md)).

**Decommissioning** the legacy Person code, its 15 test files and the dead
columns is inventoried in
[ticket 22](22-decommission-legacy-person-code-and-tests.md), gated on the
Clean MDM Person consumer being live.

## Question

Legacy `mdm_entity` rows with `entity_type = 'person'` have IDs that were
back-propagated into silver (`sec_ownership_reporting_owner.mdm_entity_id`,
`sec_adv_filing.mdm_entity_id`). Clean MDM says legacy IDs become "an
explicitly verified, versioned crosswalk," not carried IDs. For Person:
is the crosswalk built from `owner_cik`/CRD equality only (deterministic),
are legacy fuzzy-matched persons re-adjudicated or dropped, and what does
the silver back-propagation column mean after cutover (rewritten, frozen
as legacy, or dropped)?
