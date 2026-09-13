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
