# Verify S3 Request Reduction and Bronze Safety

Type: task
Status: open
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
