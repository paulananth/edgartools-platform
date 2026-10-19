# Initial and daily source loads with the Change Journal

Operator ruling, 2026-10-16: **"always load everything from source"**.
Clarification from the operator: daily processing selects changed data through
the Change Journal. Initial and daily discovery cover the entire available
delivery, without a cohort or sample limit. The preparer then selects files the
Journal does not record as processed under the same processing identity. Full
source coverage does not mean forced reprocessing of unchanged files.

The destinations in this scope are the shared local Rules, RDM and MDM stores.
Silver is excluded. Bookkeeping and the Change Journal start empty and acquire
run and processing evidence during real loads; do not populate either with
invented operational history or clear them between daily runs.

## Initial load sequence

Sources can run independently; this preferred order does not make one delayed
source hold up the others. Use the [source sequencing configuration check](specs/source-sequencing.md)
to select one source or explicitly defer a delayed source. Genuine required
inputs still block only the work that needs them.

| Order | Work | Required result before the dependent work |
| --- | --- | --- |
| 1 | Freeze a complete inventory of every retained SEC, GLEIF and OpenFIGI delivery, with its files, receipts, hashes, publication identity and time. | Every file accounted for. Full available capture and full provider coverage are separate claims; report missing pages, history or identifier coverage. |
| 2 | Load committed Rules documents and restore already published RDM code sets with exact pin equality. | Rules versions retained; required reference versions published and verified. Saving Rules is not source activation. |
| 3 | Complete supported source registration and run setup, using the existing approved mappings and matching rules. | Each source has real registration authority, supported targets, manifests, worker/verifier access and evidence. No test-helper registrations in shared stores. |
| 4 | Read the full SEC submissions population, pinned ticker catalog and full GLEIF Level 1 publication to build or verify Name Frequency. | Name counts represent the whole selected populations, never only the current bundle or matched cohort. |
| 5 | Master SEC Companies; load N-PORT registrants and applicable ADV Company evidence through their contracts. | One Company identity per accepted identity, with source records and disagreements retained. Distinct companies are not merged because their names look alike. |
| 6 | Apply GLEIF Level 1 to Companies, then its relationship and reporting-exception members when endpoints are available. | Apply current matching rules. Unmatched issuers wait; unsupported kinds remain accounted for. A full GLEIF file does not imply every record becomes a Company. |
| 7 | Master SEC Persons from all captured submissions. | Accepted people, deferred and non-Person records reconcile to the complete input. |
| 8 | Master N-PORT Fund Structures after their registrants are available. | Fund Series and registrant Company remain distinct. Missing evidence of a subfund relationship's start is not invented. |
| 9 | Read the complete retained OpenFIGI request/response set to build the approved CUSIP/ISIN agreement input; master all captured 13F Securities, then N-PORT CUSIP and ISIN-only Securities. | One identity per supported accepted identifier; ambiguous identifiers accounted for. N-PORT publications carry their quarter, publication key, revision and effective time. |
| 10 | Apply approved ownership relationships, GLEIF relationships and Security issuer links after both endpoints exist; reconcile waiting links. | Dated links point to the right Company, Person, Fund Structure or Security. Unknown endpoints or dates stay explicit. No name-based issuer shortcut. |
| 11 | Apply standalone OpenFIGI listing/ticker/exchange enrichment once its source contract is onboarded. | FIGI and ticker are cross-references/attributes under their approved mapping, not identity-matching keys. Current captured pair support is not this completed enrichment. |
| 12 | Finalize every declared run, verify all source totals and identity/link invariants, then retain a populated backup. | All declared work verified, pending Journal delivery zero, accepted/waiting/rejected totals reconciled, source and filing provenance retained. |

Batch size affects how the work is scheduled, not population coverage. Enumerate
every source key once across the complete inventory, including every bundle;
reconcile considered files as selected plus already-processed files. On an
empty Journal all are selected. Check the inventory before reporting full
coverage; do not mistake files skipped by the Journal for omitted source data.
Historical counts from the 6,414-Company cohort are not expected counts for the
full 76,230-document submissions capture or the 3,428,477-record GLEIF Level 1
publication. Derive actual full-load counts from verified results.

## Daily sequence: full coverage, changed-file processing

Use the same mapping, mastering and verification order as the initial run.
Daily describes execution cadence; it does not turn a quarterly feed into
daily source data. Capture acquisition and its provider permissions are
separate from local processing.

1. **Resume unfinished work first.** Retain its original run, inputs, leases,
   processing version and worker/verifier runtime pins. Do not create a second
   competing run over the same resources to hide a failed one.
2. **Select each source's complete available delivery.** Record its observation
   and publication times and freshness. Fresh delivery acquisition requires
   the provider authorization and qualified capture path; none is enabled by
   this plan. Replaying the same old capture is not fresh data.
3. **Validate coverage and drift.** Verify receipts and completeness before
   processing. Reuse existing approved profiling evidence when applicable;
   compare new delivery shapes against it. A new shape or code meaning follows
   the appropriate rule/reference version lifecycle, not silent normalization.
4. **Pin Rules, RDM and shared inputs.** Rebuild whole-population Name Frequency
   when its underlying complete population changes. Preserve the exact version
   used by each run. Current Rules body and reference files do not replace the
   frozen inputs of an older interrupted run.
5. **Select work through the Change Journal**, then process the selected files
   in the initial-load dependency order above. For Company and Person, omit
   `--all`: the same source, file key, content hash and processing identity is
   skipped. If every file was already processed, the preparer returns
   `manifest: null`; report a no-op without submitting an empty mastering run.
   A new/changed file, different source rule or policy, or meaningful change
   to a relevant shared input requires processing. Other source loaders need
   equivalent Journal integration before claiming this daily behavior.
6. **Reconcile links and verify results.** Check the full delivery's accounting,
   unique identifiers, surviving values and relationship dates. Reprocessing
   identical facts must not duplicate identities, source assertions or links.
   Do not create a new business revision merely because today's run has a new
   date. A genuinely new or revised source publication receives its proper
   revision and effective time.
7. **Finalize and retain recovery evidence.** Bookkeeping records work and the
   Change Journal records each file only after its merge is verified. Retain
   that evidence so future unchanged deliveries can be skipped. Explicit forced
   replays use `--all` and record `files.forced`; they are not the daily default.
   Back up after writers are idle.

### What the Journal actually compares

The implemented selector in `edgar_warehouse/mdm/clean/changed_files.py`
uses the source, file key, content hash and processing identity. Company and
Person call it before constructing their work manifests. Company includes the
logical Name Frequency content and catalog hash as shared inputs: a new capture
timestamp alone does not invalidate an unchanged Name Frequency result.

The comparison is **per file, not per row or field**. A changed multi-record
file is selected as a whole; MDM still preserves identity and write idempotency.
The `journal.record` worker records processed files after verified merges and
verifies the receipts. Plain Bookkeeping events in the Journal are not a
substitute for those file-specific records. Existing integration covers Company
and Person selection and the Journal worker; GLEIF/OpenFIGI and other unfinished
loaders must be wired and qualified rather than assumed to inherit it.

With an empty Journal, the first complete inventory selects every file. After
its verified processing is recorded, the same inventory selects zero files.
One changed file selects that file; changed rules or shared inputs may select
many unchanged files for recomputation. Do not use `--all` for either normal run.

### Source cadence and full-load meaning

| Source | Each daily execution considers | Special treatment |
| --- | --- | --- |
| SEC submissions, Company and Person | Every document in the complete capture, with required catalog, filing/page and Name Frequency inputs. | Omit `--all` from both preparers. The Journal selects new/changed or invalidated files; unchanged files produce no work. |
| SEC ownership and 13F | Every file/record in the complete declared retained scope. | Amendments and previously captured filings keep their real identities and provenance. No arbitrary first-N filing limit. |
| N-PORT | Complete retained quarter publications selected for the run, including all rows of each selected source part. | New quarter: new revision/time as supported by the contract; replay of the same quarter: same source facts. Process registrants, funds and Securities in dependency order. |
| GLEIF | The declared baseline and publication members required for complete source coverage. | Qualify publication continuity and Journal integration before daily execution. A changed bulk member may require processing all its records. Explicit deletion/status evidence controls retirement, not absence from a partial file. |
| OpenFIGI | Every retained request and response in the declared complete mapping capture. | Mapping responses cover requested identifiers, not the provider's entire instrument universe. No automatic new requests or re-download: the operator previously ruled that the capture is reused. Standalone listing enrichment still needs onboarding. |

This scope covers master/reference data and relationships accepted by the
contracts. Transactions and financial facts remain in their captured evidence;
they are not converted into MDM attributes because silver is excluded.

## What exists and what blocks the full load

The five shared stores and separate execution logins were initialized locally.
Current committed configuration has nine sources and thirteen Dataset Contracts.

| Requirement | Current state |
| --- | --- |
| Initial Rules | Nine source documents, two pipelines and one merge policy can be saved: twelve versions. They are drafts until the real lifecycle requirements are satisfied. |
| Initial RDM | Three published version-1 code sets: 309 SEC place codes, 4 place types and 20 ownership transaction codes. Restore their complete labels/crosswalks and verify their existing pins. |
| MDM registration | A source registers its datasets when its version activates: proven on a test run over captured files and approved (operator, 2026-10-19: the pipes switch on apart from live data). It must declare its acquisition feeds; live acquisition also needs a real acquisition run's proof (ticket 71). |
| Complete source runs | Company and Person have `mastering` targets; GLEIF has a merge target. Ownership, ADV, 13F and N-PORT lack complete source-owned mastering targets. The 13F reading pipeline only reads. |
| N-PORT run construction | Quarter context and publication revision/time semantics exist, but their full run builder remains ticket 79's gap. Several declared matching rules are not switched on. |
| Standalone OpenFIGI enrichment | Captured answers support N-PORT identifier agreement; listing/ticker/exchange onboarding remains ticket 80. |
| Daily automation | A proposed dependency sequence, not an installed scheduler or authorized provider acquisition. Do not revive retired daily/bootstrap commands. |

These are implementation/qualification gaps, not reasons to narrow the input
to a successful cohort or silently omit a required source. MDM completion must
wait for their supported paths; report the missing source and stage explicitly.

## Verification and recovery record

For every source record the run's full scope, considered/selected/skipped file
counts, processed-row counts, capture age, Rules and reference pins,
accepted/waiting/rejected totals, reason counts,
master and relationship counts, duplicate-identifier checks, run IDs, verification
status and backup reference. Store row-level evidence and connection files
privately; only counts and invented examples belong in this public repository.

Initial seed state is separate from the full MDM load. Rules saved, RDM
published, MDM mastered and daily scheduling enabled are four distinct claims.
