# Mastering rebuild inventory

> **Superseded in part by Claude's continuation (2026-10-02 ET),
> `.planning/workstreams/mastering-qualification-claude/TICKET.md`:**
> - The acceptance's synthetic EMPLOYED_BY link is replaced. It now uses a GLEIF accounting parent between two Companies, read by the real GLEIF reader. The test passes on PostgreSQL 16.
> - The CLAUDE.md/AGENTS.md consolidation is reverted. It is now its own ticket (`.scratch/agent-guides/issues/01-consolidate-claude-and-agents-md.md`; operator, 2026-10-02: "Split it out (Recommended)").
> - The local database inventory is done; see that ticket.
>
> Lines below that say otherwise are history.

Base: GitHub main `5b59f72ff85bfac2eda9be014cb15d7e2aa8af77` (PR #774).
Verified through the GitHub read connector. Shell fetch failed DNS; the one
missing upstream commit and its five changed blobs were imported through
read-only Git APIs and verified against their blob, tree and signed commit
SHA values before this branch fast-forwarded. Shared main was untouched.

## Active consumers

The CLI reaches Rules, Bookkeeping, Change Journal, Clean MDM, acquisition
gateways and Company silver landing. The Streamlit app imports the three
dashboard serving modules. Agent skill scripts import Change Journal's skill
interface and Bookkeeping feed resolution. ContractReader remains the
versioned consumer API, with snapshot/alias/provenance acceptance tests.
Package markers are retained. Generic identity and relationship engine tests
remain active contracts even when a kind has no current acquisition reader.

GoF review: inspected code and git history of relationships, merging,
publication, provisioning, and the three deletion candidates. Keep the shared
Merge Stage, its injected Store and LocalContractSink. The new qualification
runner is a small composition root using those tests; no class hierarchy or
new mastering engine is warranted. Deletion removes unused implementations
without changing the active variation points.

## Deleted code

| File | Caller proof |
| --- | --- |
| `edgar_warehouse/loaders/bronze_daily_index_extractors.py` | Only exported by loaders package and used by its two retired daily-index tests. No active command, capability, skill, script or dashboard calls it. |
| `edgar_warehouse/loaders/bronze_reference_extractors.py` | Only exported as seed_universe_loader. No executable caller. A dbt comment is a historical reference, not a Python importer. |
| `edgar_warehouse/mdm/clean/securities.py` | Only imported by its standalone 13F publisher test. It is outside the requested Company/Person/Relationship scope. The shared identity and typed relationship contracts are retained. |

Imports and exported names were removed from `loaders/__init__.py`.
Company submission loaders and their coverage remain.

## Removed node IDs

| Removed case | Reason and retained coverage |
| --- | --- |
| `tests/unit/test_loaders.py::LoaderTests::test_stage_daily_index_filing_loader_extracts_filing_rows` | Only retired daily-index loader; no replacement claim. |
| `tests/unit/test_loaders.py::LoaderTests::test_stage_daily_index_filing_loader_extracts_accession_from_txt_path` | Only retired daily-index loader; no replacement claim. |
| `tests/mdm/test_security_mastering.py::test_one_security_per_cusip_with_a_normalized_title` | Only deleted standalone Security publisher; no replacement claim. |
| `tests/architecture/test_boundaries.py::BoundaryTests::test_bronze_and_serving_modules_do_not_hardcode_warehouse_path_prefixes` | Iterates an empty targets list. No branch/invariant/failure remains. Active CLI and source gateway contracts stay. |
| `tests/architecture/test_boundaries.py::BoundaryTests::test_filing_document_content_uses_only_the_narrow_raw_gateway` | Iterates an empty targets list. No branch/invariant/failure remains. Active gateway boundary checks stay. |

No maintained active case was deleted as an alleged duplicate. The package-wide
publisher and path-template scans are retained: unlike the two empty-target
checks, they can fail. Counts and timing are reported separately in the ticket.

## Databases

Active logical stores: Clean MDM (`mdm` schema), Bookkeeping (`bookkeeping`
schema), Rules (`rules` schema), Change Journal (`journal` schema), with
destination-local `bookkeeping_guard` authority. Test fixtures create and
remove their own databases. Templates remain necessary during a test run.

No pre-existing database is marked unused. Live Colima/database inventory is
blocked by the stopped VM and denied Docker socket. No database or Docker
volume was deleted; no production target was selected. Historical local
`mdm`, `silver`, `bookkeeping`, `change_ledger` examples are not deletion proof.

## Qualification scope

The small fixture reads two Companies and two individual filers using the
repository's unchanged adapters and approved policy. It retains input hashes
and classification provenance. The new PG16 acceptance case checks both kinds
in one fresh store, a synthetic typed employment statement, consumer reads,
physical envelope read-back, replay idempotency and restricted-role denials.
It is collected but not database-qualified in this environment.

Existing acceptance preserves Company pagination, Rules authorization, Journal
outage/recovery, lease fencing and rollback, GLEIF parent identity/periods,
MDM publication and release security. The full local runner fails on unavailable
prerequisites and rejects skipped PostgreSQL acceptance. Hosted approval and
cutover are outside the operator-selected scope.
