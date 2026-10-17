# Source readiness and configuration-driven mastering

Status: design confirmed by the operator, 2026-10-17 07:29 ET. These are design
requirements, not claims that the runtime already enforces them. Implementation
and behavior qualification have not started. Evidence was inspected at main
`48ca68c63`; the related initializer/load guide is PR #1035.

## Confirmed dependency behavior

The operator chose: **block required inputs; let unresolved links wait**
(2026-10-17 07:26 ET).

Before a source document is processed, required approved rules, reference data
and shared inputs must be available and valid for that work. A missing required
input blocks the affected work and needs an explicit reason. It must not be
silently bypassed or treated as successful processing.

An unresolved relationship endpoint does not block independent entity facts.
Keep the unresolved relationship waiting with its source evidence so it can be
reconciled when the endpoint is available. This does not waive any required
identity evidence or permit a guessed relationship. It agrees with the existing
Security Identity definition in `CONTEXT.md`: a Security may exist before its
issuer is known.

## Confirmed synchronization behavior

The operator chose to retain the original required versions for the entire
consumer run, including resume. A newer run uses newer approved versions;
Change Journal processing identity must reflect the changed dependencies so
affected files are reconsidered even when their bytes have not changed.

Required versions include applicable source rules, Dataset Contracts, matching
and merge policy, RDM versions, Name Frequency/catalog inputs and authenticated
lookup/producer receipts. Existing runtime pins remain in force. This does not
freeze the shared MDM database: authoritative identity, constraints, leases and
fencing still need validation at commit.

Code inspection found a specific issue: `batch_input` in
`edgar_warehouse/mdm/clean/cli.py` resolves `current_reading` for each batch;
`reading_at` in `edgar_warehouse/mdm/clean/store.py` exists but has no callers.
Thus a start-of-run readiness check alone would not establish one mapping
version for every batch of that run. This is code evidence; no new behavior
test was run for this proposed change. Relevant locations are
`cli.py:137-168`, `store.py:405-430` and `run.py:82-86` in that directory.

## Confirmed execution boundary

Every source should run through one common command, with configuration defining
the source's processing. The path covers captured-file selection, dependencies,
reading, preparation, mastering, merging, independent verification and Journal
recording. Reusable engine functions are allowed; a separate preparation script
or manual sequence for each feed does not satisfy the target.

Provider acquisition remains a separate process. When an approved dependency's
source is already captured locally, the command should run the declared local
dependency first, then freeze its resulting input before starting the consumer.
Missing captures, unsupported workers or unapproved configuration stop affected
work with explicit reasons. Do not download data, invent rules or bypass source
activation. Resume unfinished work rather than creating competing runs.

Use existing Bookkeeping dependency and worker mechanisms where suitable. The
decision does not select a new workflow service, configuration schema or CLI
spelling. Define those only after inspecting the current interfaces and the
existing implementation tickets. Preserve complete source enumeration and normal
Journal filtering; neither cohorts nor forced replay are the daily default.

## Source audit

All nine sources have configured readings/mappings and thirteen Dataset
Contracts in total. **None currently satisfies the complete common-command
path without preparation or orchestration outside that path.** A source
document on disk is not proof of runtime readiness.

| Source | Current source-owned mastering target | Missing work or prerequisite |
| --- | --- | --- |
| `sec.submissions.company` | Read, prepare, merge, processed | Source-specific `prepare-clean-company` still constructs the manifest; capture/catalog/Name Frequency inputs need a common path. This is the only source declaring acquisition authority. |
| `sec.submissions.person` | Read, prepare, merge, processed | Separate `prepare-capture`; acquisition authority absent, so normal activation blocks. |
| `gleif` | Merge only | Complete member read/combine/prepare/processed path and acquisition authority absent; publication validation remains outside it. |
| `iapd.adv` | None | Monthly context, grouping/joins and complete run wiring; acquisition authority absent. |
| `sec.ownership` | None | Reading selection, owner preparation, relationship dependencies and processed accounting; acquisition authority absent. |
| `sec.thirteenf.information_table` | None; separate reading-only pipeline | Source-owned reduce/combine/prepare/merge/processed path; acquisition authority absent. |
| `sec.nport.registrant` | None | Authenticated filed-registrant lookup producer and complete run; acquisition authority absent. |
| `sec.nport.fund` | None | Filed/registrant lookup producers and complete run; acquisition authority absent. Existing deferred relationship semantics must not be invented. |
| `sec.nport.security` | None | Lookup agreement pairs, quarter context, publication identity/revision/time, issuer preparation and processed accounting; acquisition authority absent. |

Configuration evidence: Company `source.yaml:39-115`, Person
`source.yaml:112-143`, GLEIF `source.yaml:5-17`, ADV `source.yaml:1-20`,
ownership `source.yaml:1-15`, and N-PORT registrant `source.yaml:30-35`, fund
`source.yaml:33-43`, Security `source.yaml:38-48`, all under their
`rules/sources/<source>/` directory. The reading-only 13F pipeline is
`rules/pipelines/sec-13f-reading/pipeline.yaml:1-17`.

## Checks already present and gaps to close

| Boundary | Existing enforcement | Limitation |
| --- | --- | --- |
| Within a configured run | Bookkeeping validates ordered `requires` and prerequisite unit inputs (`bookkeeping/clean/config.py:50-62,102-107`, `engine.py:170-190`). | Not a universal source/entity readiness check or automatic cross-source dependency producer. |
| Run submission | Active Rules export, exact input manifest and approved rule digest (`rules/cli.py:121-127`, `bookkeeping/clean/engine.py:125-164`). | An active run target does not establish every source's completeness. |
| Source activation | Sources with MDM contracts require approved acquisition authority (`rules/db.py:187-207`). | Eight sources cannot complete normal activation yet. Do not bypass the check with disposable-test helpers. |
| Before reading bytes | Authenticates configured context and declared lookup receipts (`workers/source_read.py:102-115,309-315`). | Broader Dataset Contract/policy checks happen later, after extraction. |
| RDM | Published canonical content must match explicit version/hash pins (`rules/files.py:350-376`). | Need consistent run-wide dependency selection and retained artifacts. |
| Company preparation | Name Frequency must match capture/population; logical census content and catalog hash enter processing identity (`mdm/clean/company_prepare.py:186-208`). | Source-specific setup remains. |
| Before normalization and merge | Registered dataset and qualified policy checked (`mdm/clean/cli.py:137-168`); Merge Stage remains authoritative (`merge.py:214-232,425`). | Mapping is currently selected anew per batch; early readiness alone does not fix this. |
| Relationships | Unresolved endpoints and invalid relationship evidence retain review reasons (`mdm/clean/relationships.py:253-305`). | Reconciliation must preserve waiting evidence rather than silently dropping links. |
| Verified processing | Company/Person declare `journal.record` after merge; file identity accounts for rules/policy/shared inputs (`changed_files.py:1-30`, source targets above). | Other sources need equivalent end-to-end wiring and qualification. |

Paths in this table are relative to `edgar_warehouse/` unless otherwise noted.

## Implementation handoff

First address the mapping-version synchronization gap with a meaningful
multi-batch/resume behavior test and immutable selection, retaining commit-time
MDM safeguards. Then deepen the common execution path using existing engines
and audit each source against it. Link existing source tickets before creating
duplicates: ticket 71 covers activation/runtime gaps, ticket 79 N-PORT run
construction, and ticket 80 standalone OpenFIGI onboarding in
`.scratch/rebuild-priorities/issues/`.

Readiness claims require affected per-source behavior tests, including blocked
dependencies, permitted waiting links, pinned resume and verified Journal
recording. Static configuration inspection is the baseline audit, not those
proofs. Local test runs stay under five minutes; CI runs the full suite.

No provider request, shared database write, matching-rule change, source
activation or production deployment was performed by this interview.

Tracking: `.planning/workstreams/source-readiness/TICKET.md`.
