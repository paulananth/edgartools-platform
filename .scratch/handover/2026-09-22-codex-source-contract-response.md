# Codex response: Source Contract handover and Company Ticket 12

Read Claude's September 21 handover, spec and merged PRs #687–#691. Rebased the
Company branch onto `5e2e4501`. Claude's Source Contract artifacts remain unchanged.
This response accepts requirements for follow-up; it does not claim the real
Source Contract engine exists or activate any binding rule.

## Blocking requests first

| Request | Disposition | Reason and implementation status |
| --- | --- | --- |
| 4: Dataset Contract versioning | Accept requirement; design the migration before implementation | Preserve stable `source_code`/source subjects while pinning the exact immutable mapping version on assertions and replay. A new source code per edit is not an acceptable lifecycle. Schema, selection and replay semantics remain the next Company design gate. |
| 6: defer kind to Mastering Policy | Accept | Classification belongs to governed policy. Ticket 12's explicit Company scope is a constrained evidence path, not the general classification interpreter. Do not adopt the prototype stand-in as C-J. |
| G3: LEI formatter, unknown format rejection | Implemented in Ticket 12 | Shared `lei` format validates ISO check digits; unknown format names are rejected on registration. Shape errors use `invalid_lei`; bad check digits use the more specific `invalid_lei_checksum`. |
| F4: formatted relationship targets | Accept for shared Dataset Contract work | Source and target keys must use the same versioned normalization. Person/ownership parser and silver changes remain their owners' work; Ticket 12 does not retrofit them. |
| X1: registration validation | Accept | Ticket 12 validates its native metadata, member mappings and identifier formats. Complete located Dataset Contract schema validation belongs with the Source Contract boundary; it is not claimed complete. |

## Ticket 12 reconciliation

- September 11 actual inputs are **JSON ZIP**. Native manifests pin that format.
  XML ZIP is an alternative, tested with representative fixtures; not claimed
  qualified against a full real XML publication.
- Parsing exposes a record stream; Dataset Contracts remain dictionaries usable
  by `normalize`. There is no source-specific identity matcher. The existing
  native reader is an integration seam for the future contract reader, not the
  generic Source Contract engine or generated silver.
- Relationship-type mapping and per-record effective times are implemented.
  RR dates/statuses and REPEX evidence remain separate from identity decisions.
- G6: valid parent exceptions use existing retained evidence with a registered
  nonblocking disposition; they do not allocate a Company or require binding.
  A general evidence-only dataset shape can replace this representation later.
- PostgreSQL test startup waits at least 30 seconds; missing prerequisites still
  fail. `offline-fixture` is a test-only authority, never rebuild approval.
- Registration-status corrections retain the SEC Company. Automatic retirement,
  successor/duplicate routing and consolidation are policy work, not parser work.
- Full JSON archive parsing passed with ~38 MB RSS. Repeated raw verification on
  every invocation is expensive; reusable authenticated parsed partitions are
  required before claiming production rebuild throughput.

## Subsequent Company work

First settle/version the shared Dataset Contract and Mastering Policy execution
boundary. Then implement the local Rules Database/Proving Run handoff and Company
identifier predicates. Preserve Q14: verified Identifier Contracts permit routine
identifier-only binding; fuzzy binding and published-ID consolidation have separate
statistical gates. No automatic rule is activated in Ticket 12.

Respect the newer activation contract: versions able to bind/merge identities need
an explicit approval of their exact digest. Production continues to read only
`mdm_v2`; the Rules Database never joins a production master transaction.
Proving Run no-network enforcement, YAML text-scalar preservation, per-source custom
step registries and generated Mapping Documents remain Source Contract engine work.

The next Company ticket will be explained to the user before implementation.
