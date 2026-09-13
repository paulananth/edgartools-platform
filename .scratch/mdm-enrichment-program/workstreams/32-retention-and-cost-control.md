# Retention and cost control

Classification: cross-cutting operating workstream
Status: planned
Depends on: shared foundation evidence inventory
Future spec: `docs/specs/mdm-enrichment/retention-cost.md`

## Destination

Every source and consumer reports request, compute, storage, and validated-output
cost, while retirement and physical deletion remain distinct. Preserve
normalized evidence, manifests, hashes, run lineage, and stewardship decisions.

Define hot-to-cold transitions, rollback windows, reconstruction proof,
reference-aware retention deadlines, exact-version reviewed deletion, protected
operator authority, post-delete inventory, budgets, and alerts. Ordinary key
deletion and unreviewed lifecycle expiry cannot remove required evidence.
Archive restore has no operational recovery service level: disaster recovery
redownloads the newest complete Source Publication through the Change Ledger.
The retention specification must therefore justify archived bytes as audit
evidence rather than as a dependency of the current-state pipeline.

For new enrichment families, retain only the latest verified complete source
publication. A verified accepted replacement makes older raw bytes eligible for
Change-Ledger-authorized deletion. Keep manifests, hashes, publication lineage,
MDM Commit Evidence, and deletion evidence permanently. A lifecycle timer,
partial delta, or unverified replacement never authorizes deletion.

Daily and recovery delta bytes remain only in Temporary Bronze. Delete them
through the Change Ledger after every required consumer checkpoint and required
Snowflake and graph verification passes. Do not create a cold archive copy for
a delta. A failed or incomplete required consumer blocks deletion, not the
progress of an independent publication family.
