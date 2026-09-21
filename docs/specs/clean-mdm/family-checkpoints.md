# Publication-family checkpoints

Migration 029 adapts Claude's per-family checkpoint proposal in the existing
`mdm_v2.checkpoint` table. Its primary key is now `(consumer, source_family,
publication_family)`. Each row retains its consumed publication reference,
continuity-proof object and committed batch. Batch effects keep their immutable
copy. No source-publication table or cross-database foreign key is introduced.

## Command and manifest contract

A scoped Merge Stage command, or a batch in an existing version-2 manifest,
provides all four fields together:

```json
{
  "source_family": "fixture",
  "publication_family": "golden_copy",
  "committed_publication": "synthetic-publication-1",
  "continuity_proof": {
    "rule_version": "fixture-1",
    "inventory_digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
}
```

This example is synthetic. The existing owner-registered dataset contract must
have the matching `body.family` and include the publication family in
`body.publication_families`. Unknown family contracts fail. The runtime cannot
register that authority itself. The source adapter's continuity field definitions
belong in the same immutable dataset contract, not another registry.

`expected_checkpoint` and `checkpoint` apply to that exact tuple. A failed
Golden Copy batch cannot advance OpenCorporates, and advancing OpenCorporates
alone does not invalidate an assessed Golden Copy proposal for the same
consumer. The existing bounded transaction and publication-receipt checks apply.
`mdm mastering --model clean --manifest ...` passes these fields unchanged.

The cursor means **committed bounded progress**, not "every record in this
publication is applied." A partial batch can reference a consumed publication;
source-member completeness, all-record accounting and downstream publication
completion must still be proved independently before a run is complete.

## Source verification boundary

The capability validates family registration, complete scope metadata and the
expected/advancing cursor, and stores the supplied proof atomically. It does
**not** authenticate source artifacts or evaluate the meaning of arbitrary proof
fields. The source consumer must verify the immutable acquisition manifest and
all its members, then evaluate the versioned continuity rule before calling the
Merge Stage. The [source-only verifier](source-publications.md) now exercises that boundary
on a versioned offline fixture. Native consumer wiring and whole-publication
accounting remain required; checkpoint tests alone do not establish completeness.

GLEIF's later accepted foundation taxonomy groups Level 1, RR and reporting
exceptions into one coordinated Golden Copy publication family. Identifier
mappings remain independent, with OpenCorporates in the Company portfolio.
Three dataset codes can share that one completeness family.

## Historical compatibility and recovery

Migration preserves old cursors with empty family columns and null publication /
proof. It does not infer a family from encoded consumer strings, merge rows or
rewrite immutable batches. Old commands continue in that explicit unscoped
namespace. New scoped cursors start at zero unless approved source/rebuild
work establishes their initial state; do not copy the old counter as proof.

Previously committed commands replay with their original content hashes.
Previously staged assessments remain usable if their affected state is unchanged.
A new reversal commits a new generation and advances progress; it does not rewind
cursor history. The current cursor points to the latest batch, whose effects
retain the evidence needed to investigate or rebuild prior progress.

The migration updates only guarded checkpoint fragments in the installed core
capability and assessment snapshot function. Original migration files are
unchanged; an unexpected function shape aborts the migration. Restricted-role
writes still go through `commit_batch`, and snapshot hashes remain time-zone
independent.
