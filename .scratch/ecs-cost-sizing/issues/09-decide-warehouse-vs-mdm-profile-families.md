# Decide Warehouse Versus MDM Profile Families

Type: grilling
Status: open
Blocked by: 05, 06

## Question

Do production workloads need separate warehouse and MDM task-definition
families, or should both runtimes use one shared profile family with runtime-
specific image, command, and role data?

Evaluate the current evidence: warehouse and MDM use different immutable image
digests, dependency surfaces, commands, log-stream prefixes, and workload
failure modes, while their `small`/`medium`/`large` CPU-memory tiers currently
align. Decide whether to retain separate runtime families but standardize the
sizing-tier vocabulary, or collapse the families. The decision must preserve
image isolation, rollback clarity, IAM boundaries, workload-specific memory
floors, and an unambiguous Step Functions reference contract.
