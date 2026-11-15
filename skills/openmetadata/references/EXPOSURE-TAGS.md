# Exposure tags for managed consumers

Apply [Final exposable tables](../../data-platform/FINAL-TABLES.md). The exposure
tag's identity and exact physical-table assignments come from repository
configuration approved within requirements-and-mapping review, using profiling
evidence and the modeling decision. Use the configured classification/tag
identity; do not invent another taxonomy or infer eligibility from data class,
layer, certification, glossary membership or a table name.

Project the approved assignments into native Classification/Tag labels.
OpenMetadata is the display/readback of this decision, never a second selection
authority: a manually added tag cannot authorize mirroring or AutoOntology.
Keep internal assets documented without the exposure tag. Missing, pending,
declined or stale configuration assignments are ineligible for both consumers.

Read each table with its tags field explicitly requested and account for every
inventory page. Compare exact tagged asset identities with the configured set;
report missing and unexpected assignments independently. A missing field on a
list response is not an empty tag list. Preserve unrelated tags and curation;
if removing a stale assignment, prove it belongs to this configured projection
before using the normal scoped reconciliation path. Tag reconciliation does
not drop mirror tables, revoke source privileges or delete consumer state.

Publication is confirmed only after matching native tag readback. The mirror
and AutoOntology workflows resolve their table lists from the approved
configuration and report their own physical enforcement separately. If the
publisher or selector lacks tag support, report the capability gap; a skills
edit is not implementation or live publication. Generic projection/readback
helpers live with this skill or the application package, not under `infra/`.

