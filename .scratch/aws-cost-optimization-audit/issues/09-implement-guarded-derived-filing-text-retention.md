# Implement Guarded Derived Filing-Text Retention

Type: task
Status: resolved
Blocked by: 08

## Question

Can `sweep-filing-text` emit complete immutable, run-bound retention manifests
and can the cost optimizer use two explicitly selected successful manifests to
plan and apply deletion of eligible derived filing text without extending that
authority to Bronze evidence?

Implementation must be test-first and preserve these gates:

- evaluate exact `(accession_number, text_version)` identities, including old
  projections for CIKs that remain active;
- require two consecutive successful observations and at least 30 continuous
  days outside the required set;
- block failed, incomplete, discontinuous, unknown-version, or drifted inputs;
- bind the reviewed plan to complete manifest hashes and exact S3 `Key` plus
  `VersionId` targets;
- retire and verify the matching Silver registration before S3 deletion;
- record durable preflight, retirement, deletion, and post-delete evidence;
- leave every Bronze filing artifact and version untouched; and
- rebuild later-required projections from retained Bronze evidence.

## Answer

Implemented test-first. `sweep-filing-text` now publishes complete immutable,
predecessor-linked manifests whose exact not-required identities carry their
continuous streak start. Each manifest's required and processed sets come from
one post-projection Snowflake snapshot and bind its real query ID plus content
hash; an extracted row that is not yet visible in canonical Snowflake makes the
manifest incomplete. The cost optimizer builds a hash-bound plan from two
consecutive successful observations, records and verifies Silver retirement,
rechecks the live canonical required set, verifies the latest manifest and
exact S3 version inventory, and deletes only the reviewed derived-text
`Key`/`VersionId` targets.

Retirement and apply publish evidence to the protected warehouse release
prefix before deletion. Apply holds a shared versioned S3 mutation lock that
filing-text projection writers also honor, and both runtime and operator IAM
release only that exact lock VersionId. Unknown versions, incomplete or
discontinuous observations, identity drift, a newly required identity, active
Silver rows, evidence-publication failure, and S3 version drift all fail
closed. Bronze paths are outside the accepted target grammar.

Verification after rebasing onto current `origin/main` and rebuilding the
environment: 71 focused and architecture tests pass; Ruff, targeted Pyright,
Terraform formatting, and diff checks pass. The full suite
completed with 3197 passed, 7 skipped, and 8 pre-existing PostgreSQL integration
failures caused by the current test database lacking
`source_fetch_work.captured_etag`; this branch does not touch that schema or
those acquisition-ledger/conflict tests.
