# Native GLEIF Company evidence

Ticket 12 adds a native evidence path to the existing Clean MDM commands. It does
not activate Company matching rules or implement the Source Contract runner.
The September 11 captured source is **JSON ZIP**. XML ZIP is an explicit alternative
input format; callers must pin the actual format, never infer it from a filename.

## Contracts and source authority

`gleif_source.dataset_contract(member)` returns a reviewable Dataset Contract for
`level1`, `relationships` or `reporting_exceptions`. It does not register it.
Owner registration still requires the existing approved acquisition registry.
Tests use the named `offline-fixture` authority in disposable PostgreSQL 16 only.
Do not copy that authority into a real rebuild.

Register an aggregate dataset with the existing `publication_contract` and:

```json
{
  "native_contract": {
    "version": "gleif-native-record-v1",
    "record_sources": {
      "level1": "gleif.level1.v1",
      "relationships": "gleif.relationships.v1",
      "reporting_exceptions": "gleif.reporting_exceptions.v1"
    },
    "company_leis": ["<explicit approved Company LEI>"]
  }
}
```

The aggregate uses publication family `golden_copy`, exactly these three members,
a pinned replacement scope, and parser/contract version `gleif-native-record-v1`.
Record datasets must match its source family and native member/schema version.
OpenCorporates remains a different corroboration publication; it cannot replace
any Golden Copy member or connect a Golden Copy recovery chain.

The captured publication manifest extends `clean-mdm-publication-v1`:

- `publication_time`: publisher release timestamp with timezone;
- `sequence`: exact UTC microseconds since 1970 (`release_sequence`);
- each member's `native`: `format` (`json.zip` or `xml.zip`), `cdf_version`
  (`LEI_3.1`, `RR_2.1`, `REPEX_2.1`), `content_date`, `file_content`,
  `delta_start`, and exact integer `record_count`;
- full coverage: `GLEIF_FULL_PUBLISHED`, no delta start or predecessor;
- delta coverage: `GLEIF_DELTA_PUBLISHED`, exact predecessor sequence AND captured
  manifest hash. Each member's delta start must equal its predecessor's content
  date. Unknown/missing metadata fails; there is no filename-based repair.

JSON files have no XML header. Their metadata must be pinned in the captured
manifest from publisher metadata. The historical qualification uses the frozen
publisher release time as JSON content time; it does not invent XML header proof.
XML headers must agree with the pinned metadata. The members can have different
content times, but none may exceed the coordinated publication time.

`inspect_archive` produces the three hashes required when recording acquisition
revisions: raw archive SHA-256; SHA-256 of canonical JSON records followed by
newlines in source order; and a version/member-tagged hash of that retained record
content. The domain hash covers all retained native evidence, not just selected
master fields. Repacking a ZIP does not change the latter hashes. Cross-format
XML/JSON equivalence is not claimed for source structures with different array or
attribute representations. Original bytes and publisher metadata remain in the
acquisition archive/manifest independently of selected master values.

## Bounded consumption and recovery

Use the existing version-2 mastering manifest, with `native_source`:

```json
{
  "source_code": "gleif.publication.v1",
  "publications": ["<captured manifest revision UUID>"],
  "target_sequence": 1789142400000000,
  "previous_run_id": "<fully consumed predecessor root UUID, or omit>"
}
```

Every batch has `native_input` with `publication`, `member`, zero-based `offset`
and `count` (at most 1,000). Supply complete, nonoverlapping ranges for every member
of every publication selected by the recovery plan, in publication order. An empty
member needs one `(offset=0,count=0)` batch. Preserve normal batch IDs, consumer,
family checkpoint positions, policy digest and `as_of`. A native batch cannot also
supply inline assertions/deferred records, generic input or caller proof metadata.
Explicit governed decisions remain the existing Merge Stage interface.

Set `MDM_SOURCE_ARTIFACT_ROOT` to the approved local directory, or an S3 prefix for
AWS operation. Acquisition references outside that root are refused. Existing
`MDM_DATABASE_URL`, `BOOKKEEPING_DATABASE_URL`, `CHANGE_LEDGER_DATABASE_URL` and
runtime role settings apply. The acquisition reader uses processor read privileges.

```bash
uv run edgar-warehouse mdm mastering --model clean \
  --manifest "$CLEAN_MDM_MANIFEST" --run-id "$CLEAN_MDM_RUN_ID" --limit 1000
```

Verification finishes before a root run or master transaction is written. At most
128 candidate publications are considered. The plan, proof digests, record Dataset
Contract digests and every required range are frozen in existing `PipelineRun`
scope. Each atomic MDM commit retains its authenticated range, exact
normalized/deferred counts, source assertions/evidence, assessment, family cursor
and outbox intent. A retry cannot replace the frozen input. No new control ledger
or cross-database transaction is introduced.

`source_delivery_verified` means all source bytes/counts/hashes passed.
`source_consumption_complete` additionally means every required range has an
observed commit with matching proof, record count and source/publication metadata.
Only this gate authorizes a predecessor, not a partial checkpoint. It does not
require downstream delivery to finish first. `end_to_end_complete` also requires
all ordinary reviews and publication receipts. Lost export/graph acknowledgements
are recovered through the existing idempotent outbox.

## Evidence and publication semantics

Only approved LEIs with eligible Company categories are normalized. Names and
addresses stay in full source provenance; approved GLEIF fields use their own
names and the shared field-priority policy. LEI checksums are validated by the
shared `lei` formatter. Unknown format names fail Dataset Contract registration.

RR preserves source direction, direct versus reported ultimate accounting types,
source statuses and dated relationship periods. Endpoints must be approved
Companies. Missing/ambiguous periods and unsupported relationship types are
retained as blocking evidence. Shared projection rejects cycles, conflicting
parents, self-links and incompatible endpoints; calculated ultimate parents stay
separate. Relationship source bindings still require the governed policy path.

REPEX retains exception reasons; it never fabricates a parent edge or a Company
identity. Registration status corrections update source facts. They cannot retire
an SEC identity, redirect a duplicate LEI or approve consolidation themselves.
Those actions require the future governed Company rules.

Migration 030 permits `nonblocking_deferred_reasons` in an immutable Dataset
Contract. Native GLEIF declares approved-scope exclusions, supported other identity
kinds, and valid reporting exceptions as retained, nonblocking evidence. Malformed
LEIs, unknown kinds and source integrity problems remain blocking. The SQL commit
capability enforces the registered disposition, exact accounting and retention;
runtime callers cannot close or reclassify that evidence. Old datasets continue to
block all deferred records. No historical migration file is modified.

## Qualification and limits

See [archive results](../../../.scratch/clean-mdm/ticket12-native-qualification.json)
and [acceptance report](../../../.scratch/clean-mdm/ticket12-acceptance.md).
The real archive scan verified 10,267,595 records and 1,026,223,252 compressed bytes,
with a peak process RSS of 37,801,984 bytes on the test Mac.

Limits: one unencrypted ZIP entry, 1 GiB compressed, 16 GiB expanded, 1 MiB per
canonical record, 64 JSON nesting levels, 16 MiB retained input per invocation,
32 MiB command manifest. XML disables DTD/entity/network expansion and parser
large-tree mode. Exact counts, CRC, hashes and EOF checks fail closed.

The full real JSON archives passed; XML qualification uses representative
fixtures and fault cases, **not a full real XML Golden Copy**. Full archive
verification currently repeats per invocation and took approximately 20 minutes
for this snapshot. Memory and commit bounds are proved; production rebuild
throughput is not. The Source Contract runner should produce authenticated,
immutable parsed partitions so resume does not reparse all raw archives. No hosted
cutover, all-global mastering, source deletion or automatic rule activation is
approved by this ticket.
