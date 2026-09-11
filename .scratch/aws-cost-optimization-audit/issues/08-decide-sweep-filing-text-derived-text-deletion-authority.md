# Decide Whether Filing-Text Sweep Can Authorize Derived-Text Deletion

Type: grilling
Status: resolved
Blocked by: 07

## Question

May `sweep-filing-text` become the semantic authority for permanently deleting
obsolete derived filing-text projections, while remaining explicitly unable to
authorize deletion of their underlying immutable Bronze filing artifacts?

If yes, what durable candidate output, observation/grace period, exact-version
binding, Silver retirement, review, and post-delete evidence must separate the
sweep's `required`/`processed` decision from the destructive apply operation?

## Comments

- 2026-09-07: The user confirmed that `sweep-filing-text` may authorize
  deletion of obsolete derived filing text only. Its authority does not extend
  to the underlying immutable Bronze filing documents or attachments.
- 2026-09-07: The user accepted two consecutive successful not-required
  observations plus a 30-day grace period. Cleanup retires the corresponding
  Silver registration first, verifies that retirement, then deletes the exact
  reviewed S3 object version and records post-delete evidence. If the CIK later
  becomes required again, the sweep rebuilds the derived text from retained
  Bronze evidence.

## Answer

Resolved 2026-09-07. `sweep-filing-text` may become the semantic authority for
retiring and permanently deleting obsolete derived filing-text projections,
but it cannot authorize deletion of an underlying immutable Bronze filing,
document, attachment, or source-evidence version.

Decision contract:

- Required and obsolete status is evaluated for the exact
  `(accession_number, text_version)` identity, not for the CIK alone. An older
  projection may therefore become obsolete when the same active CIK has a
  newer required filing. An unknown or unclassified text version is blocked.
- Eligibility requires the exact identity to appear as not required in two
  consecutive successful sweeps and to remain continuously not required for
  at least 30 days. Failed, incomplete, missing, or discontinuous observations
  cannot advance the gate.
- Every successful sweep emits an immutable, complete manifest pinned to its
  run and Snowflake publication identities. It includes the full required,
  processed, and not-required identity sets plus counts and hashes. CloudWatch
  logs and bounded samples are diagnostic only and cannot establish authority.
- The deletion planner compares explicitly selected prior and current
  manifests. It first emits a separately reviewable, hash-bound plan containing
  exact S3 `Key` and `VersionId` targets; it does not infer eligibility from an
  unbounded S3 listing or mutable latest state.
- Apply first retires the matching Silver registration and verifies that
  retirement. Only then may it delete the exact reviewed S3 object version and
  persist post-delete evidence. Drift, a new requirement, a replacement
  version, or an incomplete evidence chain fails closed.
- A later return to the required set rebuilds the derived projection from the
  retained Bronze evidence rather than restoring a deleted derived object.
