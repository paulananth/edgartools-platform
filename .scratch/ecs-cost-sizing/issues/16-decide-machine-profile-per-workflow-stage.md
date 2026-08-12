# Decide the Machine Profile for Every Workflow Stage

Type: grilling
Status: open
Blocked by: 03, 06, 12, 13

## Question

Which warehouse or MDM `small`, `medium`, or `large` profile should each
retained workflow stage use after accounting for historical peak and sustained
CPU/memory, records per item, concurrency, duration, failure/OOM history, and
cost and time per successful output?

Retain separate warehouse and MDM runtime families unless the profile-family
decision says otherwise, but use one sizing vocabulary and one canonical
selection contract. Do not infer a downgrade from a sparse family-level
average. Require execution-level evidence for the actual workload class and
preserve documented memory floors for gold and residual-holds/security work.
Where two profiles are correct and stable, prefer the one that materially
shortens end-to-end completion on the accepted cost frontier; do not downsize
solely because the smaller profile is cheaper.

The full-canonical SeedUniverse stage is already fixed at warehouse `large`
after a live 4-GiB OOM; the dormant batched workflow's medium reference has no
production execution evidence and is not counterevidence. This decision may
refine bounded seed and parsing utilities, but it cannot lower
`warehouse.full_canonical_seed` without a new three-canary high-risk evidence
cohort. Keep `mdm-large` operational until the accepted representative,
non-zero-data `mdm-medium` canaries pass; after acceptance, its normal binding,
registration, bake protection, rollback, and emergency-use rules follow
**Decide Warehouse Versus MDM Profile Families**.
