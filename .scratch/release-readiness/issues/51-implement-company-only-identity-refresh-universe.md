# Implement the company-only identity refresh universe

Type: task
Status: claimed
Blocked by: 50

## Question

How must scheduled company-identity processing implement the company-eligible
universe decided by
[Research the SEC-listed company universe for bounded daily loads](50-research-sec-company-universe-for-daily-load.md)
without narrowing filing ingestion or MDM relationship processing?

## Required work

- Define one reusable eligibility boundary over active tracked CIKs:

  ```text
  entity_type = operating
  OR CIK is present in the current official SEC ticker snapshot
  ```

- Use the boundary in both identity modes:
  - Daily Identity Refresh: forced seven-day impacted-CIK union intersected
    with the company-eligible universe.
  - Identity Backstop Sweep: complete company-eligible universe, not the
    approximately 26,300-CIK all-entity tracked universe.
- Read ticker eligibility from the captured canonical SEC reference snapshot;
  do not make a second untracked network fetch and do not hard-code the
  current 3,243 count.
- Emit the reference-snapshot identity, input counts, eligible counts,
  excluded counts, exact processed CIK digest, and elapsed time.
- Preserve explicit-CIK operator repair paths.
- Prove filing ingestion and MDM all-entity relationship processing do not
  inherit this filter.
- Update the manual timing/coverage evidence contract in
  [Implement and Activate the Bounded Daily Identity Refresh Schedule](49-implement-bounded-daily-identity-refresh-schedule.md)
to require exact company-eligible-universe parity rather than all tracked CIKs.

## Done when

Focused and architecture tests prove both identity modes use the same
company-eligibility contract, the old all-entity window cannot re-enter either
scheduled identity path, non-company relationship entities remain available
to their own workflows, and Release-Candidate-bound execution evidence records
the exact universe and duration.
