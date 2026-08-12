# Decide and Capture the Protected Rollback Cohort

Type: grilling
Status: open
Blocked by:

## Question

Which exact six warehouse/MDM task definitions and immutable image digests are
the protected production rollback cohort, and what evidence is required before
cleanup may rely on that designation?

Research rejected the last captured pre-handoff live cohort:
warehouse `small:159`, `medium:164`, and `large:157` on digest
`sha256:a493e0d183f4bd1d5a01f46034b2250d76830206b49672b5f14d9a35080e504e`,
plus MDM `small:137`, `medium:138`, and `large:72` on digest
`sha256:cc64ba854ee382256fe7f58381f57feadd923645507bac53cf7e0c57a4e4640a`.
Both digests retain immutable role/source tags, but the only execution in their
exact deployment window failed before graph and gold completion, and both
images predate production-observed fixes. They are recovery evidence, not an
approved known-good release.

Decide between these evidence-backed choices:

1. Persist the current six revisions as the release baseline and retain one
   canonically identical earlier six-revision cohort (`164/168/161` warehouse,
   `141/141/75` MDM) as control-plane recovery, explicitly acknowledging that
   it is not an independent code rollback.
2. Build and rehearse a separate immutable post-fix image pair through the
   bounded full-chain contract before designating it as a code rollback.

Persist the decision with exact ARNs, digests, role source commits/tags,
generated-definition compatibility, evidence hashes, and an operator
attestation. Revision adjacency or `latest-N` is not acceptable rollback
evidence.
