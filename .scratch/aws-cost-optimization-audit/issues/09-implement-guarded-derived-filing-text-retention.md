# Implement Guarded Derived Filing-Text Retention

Type: task
Status: claimed
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
