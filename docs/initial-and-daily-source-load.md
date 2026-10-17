# Initial and daily full-source loads

Operator ruling, 2026-10-16: **"always load everything from source"**.
Initial and daily processing cover the entire available delivery of each source.
Use batches to divide that work, never a cohort, sample limit or changed-file
filter. Repeating unchanged source evidence must remain idempotent.

The destinations in this scope are the shared local Rules, RDM and MDM stores.
Silver is excluded. Bookkeeping and the Change Journal start empty and acquire
run and processing evidence during real loads; do not populate either with
invented operational history or clear them between daily runs.

## Initial load sequence

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
every selected key once across the complete worklist, including every bundle;
check the union against the source inventory before reporting a full load.
Historical counts from the 6,414-Company cohort are not expected counts for the
full 76,230-document submissions capture or the 3,428,477-record GLEIF Level 1
publication. Derive actual full-load counts from verified results.

## Daily sequence: full deliveries again

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
5. **Process every source record**, in the initial-load dependency order above.
   For Company and Person preparers, `--all` disables the existing processed-file
   skip. Include it for every bundle and exhaust the complete worklist. Other
   loaders must expose equivalent full-delivery selection before use; do not
   invent an option or treat a read-only target as a mastering load.
6. **Reconcile links and verify results.** Check the full delivery's accounting,
   unique identifiers, surviving values and relationship dates. Reprocessing
   identical facts must not duplicate identities, source assertions or links.
   Do not create a new business revision merely because today's run has a new
   date. A genuinely new or revised source publication receives its proper
   revision and effective time.
7. **Finalize and retain recovery evidence.** Bookkeeping records work and the
   Change Journal records verified outcomes, even for forced full processing.
   Keep them for recovery and auditing; their contents do not justify skipping
   source records under this full-load policy. Back up after writers are idle.

### Source cadence and full-load meaning

| Source | Each daily execution processes | Special treatment |
| --- | --- | --- |
| SEC submissions, Company and Person | Every document in the selected complete capture, with required catalog, filing/page and Name Frequency inputs. | `prepare-clean-company --all` and `prepare-capture --all` per bundle; no subset of recently changed CIKs. |
| SEC ownership and 13F | Every file/record in the complete declared retained scope. | Amendments and previously captured filings keep their real identities and provenance. No arbitrary first-N filing limit. |
| N-PORT | Complete retained quarter publications selected for the run, including all rows of each selected source part. | New quarter: new revision/time as supported by the contract; replay of the same quarter: same source facts. Process registrants, funds and Securities in dependency order. |
| GLEIF | A complete Golden Copy baseline of all declared members and records in scope. | A delta alone does not meet this full-load policy. Any future delta-based capture must first produce a proven complete snapshot; that reconstruction is not assumed implemented. Explicit source deletion/status evidence controls retirement, not absence from a partial file. |
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
| MDM registration | Only SEC Company currently declares acquisition authority. Source activation/handoff requires real authority; the other sources cannot be registered merely because their proofs used disposable stores. Ticket 71 tracks part of that work. |
| Complete source runs | Company and Person have `mastering` targets; GLEIF has a merge target. Ownership, ADV, 13F and N-PORT lack complete source-owned mastering targets. The 13F reading pipeline only reads. |
| N-PORT run construction | Quarter context and publication revision/time semantics exist, but their full run builder remains ticket 79's gap. Several declared matching rules are not switched on. |
| Standalone OpenFIGI enrichment | Captured answers support N-PORT identifier agreement; listing/ticker/exchange onboarding remains ticket 80. |
| Daily automation | A proposed dependency sequence, not an installed scheduler or authorized provider acquisition. Do not revive retired daily/bootstrap commands. |

These are implementation/qualification gaps, not reasons to narrow the input
to a successful cohort or silently omit a required source. MDM completion must
wait for their supported paths; report the missing source and stage explicitly.

## Verification and recovery record

For every source record the run's full scope, file/row counts, capture age,
Rules and reference pins, accepted/waiting/rejected totals, reason counts,
master and relationship counts, duplicate-identifier checks, run IDs, verification
status and backup reference. Store row-level evidence and connection files
privately; only counts and invented examples belong in this public repository.

Initial seed state is separate from the full MDM load. Rules saved, RDM
published, MDM mastered and daily scheduling enabled are four distinct claims.
