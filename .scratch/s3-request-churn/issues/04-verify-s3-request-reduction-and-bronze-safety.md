# Verify S3 Request Reduction and Bronze Safety

Type: task
Status: superseded by the rebuild (2026-10-13 17:31 ET): the pipeline it changes (the retired pipeline's S3 paths) was retired (platform validation 2a/2b, #764 and #766; the DuckDB silver store, silver-merge-engine-migration 17); the configured platform (Rules, Bookkeeping, Change Journal, Clean MDM) replaces it. Reopen as a new ticket if the need still applies
Blocked by: 03

## Question

Does an immutable-image production rerun of the same representative workload
demonstrate the expected Tier-1 request reduction while producing identical
business outputs and preserving Bronze immutability and idempotency?

Compare baseline and candidate by bucket, prefix, operation, workflow, elapsed
time, and request-estimated cost. Fail closed on unexplained output drift,
additional SEC fetches, missing artifacts, checksum changes, conditional-write
regressions, manifest incompleteness, or an unattributed request remainder over
5%. Disable temporary attribution metrics after evidence capture unless their
ongoing value and bounded cost are explicitly accepted.
