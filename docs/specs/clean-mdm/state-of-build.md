# Clean MDM state of the build

Checkpoint: 2026-09-19. This is a local development handoff, not a release or
cutover approval. The shared core and first native Company preparation path
are implemented; the complete redesign remains in progress.

## Current continuation — native Company evidence, 2026-09-22

Ticket 12 is implemented on `codex/company-native-gleif`, rebased through
`origin/main` `5e2e4501` (#691). PR #673 already merged the prior Company foundation;
the older stacked-branch instructions below are historical.

Native JSON ZIP/XML ZIP verification, authenticated bounded ranges, frozen recovery
plans and exact whole-publication consumption now feed the existing Merge Stage.
Migration 030 permits declared nonblocking retained evidence while preserving
blocking source errors. SEC + GLEIF Company field provenance is exercised on a
retained source fixture with an explicit test binding. No automatic rule is active.

See [native operations](native-gleif.md), [Ticket 12 acceptance](../../../.scratch/clean-mdm/ticket12-acceptance.md)
and [response to Claude](../../../.scratch/handover/2026-09-22-codex-source-contract-response.md).
The complete September 11 JSON archives passed streaming checks (10,267,595 records,
~38 MB RSS). Full production consumption throughput and real XML snapshot qualification
remain unproved; bounded invocations currently reparse all raw archives.

Next: Company matching/mastering through the shared Dataset Contract versioning and
Mastering Policy execution boundary, aligned with the Source Contract design.
Claude can own that follow-up after this PR lands, on a dedicated branch. The
handover must preserve Company Q14, separate fuzzy/consolidation qualification and
explicit approval before activating a binding-capable rule digest. Do not start
Person integration ahead of the Company completion gate.

## Prior continuation — source-only Company prerequisite, 2026-09-20

Ticket 11 is implemented on `codex/company-publication-verification` in
`../edgartools-platform-company-publication-verification`, based on the unmerged
Company branch at `7784c0e3`. The PR is stacked on `codex/sec-gleif-company`;
merge its parent first, then rebase/retarget this increment before landing on main.
Existing worktrees are preserved; `.planning/active-workstream` is unchanged.

The [source-publication verifier](source-publications.md) checks retained manifest
and member bytes against immutable acquisition evidence, distinguishes delivery
from source coverage and proposes deterministic per-family recovery. The synthetic
fixture publishes zero domain records. No new table, role, migration or native
consumer activation was introduced. The existing generic CLI still accepts caller
proof metadata; native source consumers must call the verifier before Merge Stage.

Verification: 89 broader tests and 12 final continuity tests passed without skips
(11 overlap; 90 distinct cases). [Evidence](../../../.scratch/clean-mdm/company-publication-acceptance.json)
pins commands, report hashes and the final guard's targeted verification.
[Review](../../../.scratch/clean-mdm/company-publication-review.md) records boundaries.
No persistent local database changes, hosted deployment or source deletion occurred.

Next is [ticket 12](../../../.scratch/clean-mdm/issues/12-integrate-native-gleif-company-publications.md):
qualify native GLEIF metadata and normalization, integrate verified batch membership
and exact whole-publication consumption accounting. SEC + GLEIF Company mastering
and its matching qualification remain incomplete; continue Company before Person.

## Prior continuation — Company pickup on 2026-09-20

Rebased onto `origin/main` `dc55bf1d`; Company scope remains in
`codex/sec-gleif-company`. [Latest pickup reconciliation](../../../.scratch/handover/2026-09-20-codex-company-enrichment-reconciliation.md)
records the disposition of Claude’s proposals and differences from the newer
accepted Company policy. Assessment work is preserved as `f3f924a9`.
Migration 029 adds family-scoped cursors and existing-manifest support; see
[family checkpoints](family-checkpoints.md). All 47 current Clean MDM PostgreSQL
and native Company checks passed without skips; [evidence](../../../.scratch/clean-mdm/company-family-checkpoint-acceptance.json)
pins the tested files. The next prerequisite is
[ticket 11](../../../.scratch/clean-mdm/issues/11-verify-enrichment-publication-inventory.md),
immutable source inventory/continuity verification. Neither checkpoint metadata
nor an assessment proves GLEIF source completeness or matching qualification.

## Prior continuation — after merge and Claude handoff

PR #657 merged as `e2807e52` after all seven CI checks passed, including all
83 PostgreSQL integration tests without skips. The CI-image prerequisite and
conflict-fixture migration gap mentioned later in this checkpoint were fixed.

Continue in `../edgartools-platform-sec-gleif-company` on
`codex/sec-gleif-company`, rebased onto `b87fc05a` (PRs #658/#659 included).
[Company Q1–Q13](company-policy.md) supersede the old manual-default and
blanket deferred-match completion rules. Read the
[handoff reconciliation](design-reconciliation-2026-09-19.md).
[Design gate 08](../../../.scratch/clean-mdm/issues/08-confirm-company-candidate-assessment.md)
is accepted; the candidate-assessment foundation is implemented in
[ticket 09](../../../.scratch/clean-mdm/issues/09-build-company-candidate-assessment.md).
The earlier integration worktree is preserved.

Candidate-assessment checkpoint (2026-09-20): migration 028 retains every
proposed binding/consolidation before application; shared `apply()` proceeds
without a new manual pause. Rejected proposals retain veto/context; application
revalidates affected state, supersedes stale proposals and retries boundedly.
Applied events commit with the master journal/checkpoint/outbox. Preview stays
rollback-only. [Recovery API](candidate-assessments.md).

Verification: 665 broader checks passed; final assessment changes passed 9
focused PostgreSQL tests, all without skips (overlapping suites). Source hashes
and reports: [assessment evidence](../../../.scratch/clean-mdm/company-assessment-acceptance.json).
No persistent schema/data migration or hosted deployment occurred. Fuzzy
matching, rule qualification and complete SEC + GLEIF Company mastering remain
unimplemented; this is an assessment foundation checkpoint.

The sections below describe the original check-in and its evidence. Where its
branch, PR-draft status or next steps differ, this continuation takes precedence.

## Start here and preserve ownership (original checkpoint)

- Continue from branch `codex/clean-mdm-integration` in
  `../edgartools-platform-clean-mdm-integration` or create your own runtime
  branch/worktree from its published head. Do not commit on another runtime's
  branch. Fetch and inspect live status before choosing the next task.
- User explicitly assigned this fresh integration branch after Grok PRs #655
  and #656 merged into `origin/codex/clean-mdm` at `608a5991`.
  Their changes are preserved. Rebase onto `origin/main` at `5fe70798`
  produced baseline `e14eb74b`; the tree difference from `608a5991` was only
  upstream `CLAUDE.md`. The remote `codex/clean-mdm` branch was not rewritten.
- The old `../edgartools-platform-clean-mdm` worktree and backup branch
  `codex/backup-clean-mdm-20260918-29eea4d1` remain rollback anchors.
  The primary checkout and `.planning/active-workstream` (`fix-pipelines`)
  belong to other work; do not repurpose them.
- Authoritative frontier: [Wayfinder map](../../../.scratch/clean-mdm/map.md)
  and its numbered issues. Ticket 04 remains claimed/incomplete; tickets
  05–07 are not fully delivered. Do not infer completion from branch names.

## Accepted decisions

Q1–Q16 are settled in the policy ticket. Company and Person have immutable
internal identities and governed profiles; Security remains distinct. Master
field selection is deterministic by type and field. Null/unknown does not erase
known values; clear/retract is explicit. Reviewed merges retain aliases and can
be reversed by evidence replay with dependency checks and Match Exclusion.
Unqualified automatic matching remains disabled pending independent calibration.

The current qualification target is **local PostgreSQL 16**. Snowflake Postgres
qualification is deferred. Retain the old MDM for **30 days after cutover**;
there has been no cutover and no retention clock has started. Ask at most three
questions at a time; do not reopen accepted policy choices.

Master state, its transactional journal, checkpoints and durable publication
intent share `mdm`. `change_ledger` owns acquisition history and an idempotent
MDM event mirror; `bookkeeping` owns the existing root `pipeline_run`. Preserve
one root run UUID across stores; do not claim cross-database atomicity.

## Implemented behavior

| Area | Current implementation | Limit |
| --- | --- | --- |
| Shared merge | Reviewed bindings, kind/identifier conflicts, deterministic fields and role fields, aliases, replay reversal and exclusions | Automatic rules disabled; closure capped at 10,000 records |
| Relationships | Typed endpoints, dated roles/edges, cycle/parent/interval checks and reprojection | Full native pipeline integration pending |
| Recovery | Restricted PostgreSQL capability, atomic batch/evidence/checkpoint/outbox, attempt journal, fenced ordered retries, three-database reconciliation | Large-component staged reversal not implemented |
| Source preparation | `mdm prepare-clean-company`, bounded immutable Parquet/JSONL bundle with dataset/policy/manifest inventory | SEC `operating` and qualifying `other` filers; pinned Company, filings, and ticker members; explicit sample, no retirement by absence |
| Source defects | Migration 027 retains unsupported/malformed records and requires exact accounting plus an open blocking review in every observing batch | Reviewed deferred-resolution lifecycle remains unimplemented |
| Consumer reads | Opt-in authenticated v2 shared identities, aliases, field/profile provenance and historical pagination | Legacy API remains the default |
| Publication | Real journal mirror; idempotent verified local export/graph contract files | Local files are not hosted export/graph materialization |
| Grok integration | Separate Change Ledger URL, optional local silver PostgreSQL reader, bounded legacy Company mastering | Local reader lacks `QUALIFY` translation; local loader assumes one file per table |

Native assertions retain source provenance independent of transport member
hash/path/line position. Identical rows and overlapping bounded samples remain
one business assertion. Input occurrence counts remain in batch accounting;
transport bytes and inventories remain pinned. Malformed fields cannot inject
normalized `op` objects; nonfinite JSON numbers are retained as malformed bytes.
SQL rejects missing, closed or retired deferred reviews, including replay into
a new batch, and rolls back the entire transaction on evidence collisions.

## Local state and pinned input

The user supplied local URLs for databases `mdm`, `bookkeeping` and
`change_ledger` on `127.0.0.1:5432`. Keep credentials in environment variables,
not new committed artifacts. Grok also provisioned the local `silver` database.
The latest read-only check found PostgreSQL 16.15, 13 legacy MDM entities,
3 silver companies, zero Clean MDM batches/datasets and zero acquisition
registry versions. Migration 027 is **tested in disposable databases but not
installed in the persistent local MDM**. Migrations 023/025/026 and mirror 024
were previously installed there; keep their checksums unchanged.

The prepared candidate is at:

```text
~/.local/share/edgartools/clean-mdm/inputs/local-fewco-20260917-company-v2/
```

It contains Apple (CIK 320193), Microsoft (789019), and Amazon (1018724), sourced
from Grok's captured run `local-fewco-20260917`. No new SEC requests were made.
The full source member hash is
`81c9914a076df5d676f54eb814611a20fc5d3deb891aaf3f6e14fc7e223f62b8`.
The JSONL hash is
`765a2983e9eed562c499801103a1867a3da339ad8e1c0e6ad987760293c5b00f`.
`inventory.json` pins all six bundle members. The earlier `company-v1` directory
is an unexecuted preparation draft; retain it but use the corrected `company-v2`
dataset contract. The suffix describes the local bundle revision, not a new
source schema version.

Preparation does not activate registry coverage, register policies, bind
identities, or execute the manifest. The user asked for an explanation of
pinned inputs but has not explicitly selected this candidate for rebuilding.
Present this concrete candidate when that decision is needed. Never fabricate
an active registry row or treat a three-company sample as complete coverage.
`last_synced_at` is observation time, not source effective time; the candidate
policy explicitly permits unknown effective time.

## Verification and review

Final verification: **134 passed, 0 failed, 0 skipped in 83.20 seconds**
(31 PostgreSQL integration tests, 3 native Company unit tests, and 100 related
API/publication/local reader/acquisition checks). The exact command, source
hashes, migration checksums and JUnit path are in
[integration acceptance evidence](../../../.scratch/clean-mdm/integration-acceptance.json).
The suite exercises real disposable PostgreSQL 16 with restricted application
roles and fails, rather than skips, missing prerequisites. It also runs API,
publication, local silver reader and acquisition-engine regressions. No Snowflake
credentials or live downstream services are required.

The Standards, Spec and GoF reviews of this increment completed independently.
Spec review found and verified fixes for duplicate assertion identity,
malformed field handling and SQL review omission; the follow-up also closed
an existing-deferred/new-run omission. Standards review found the overflowing
`1e999` JSON case, now covered. No remaining blockers were reported in this
increment; no structural GoF refactor was justified. See
[review record](integration-review.md). This does not retroactively certify
the entire legacy platform or all unimplemented acceptance gates.

Ruff passes for the Clean MDM package and changed acceptance tests. A broader
check also reported existing lint violations in legacy `mdm/cli.py`; this
checkpoint does not claim repository-wide lint or test success.

## Next agent: ordered work

Priority update, 2026-09-19: the user requires **SEC + GLEIF multisource
Company mastering before other entity integrations**. Follow the
[Company completion gate](company-completion.md); the SEC-only pilot is a
preparation check, not Company completion. PR #657
(https://github.com/paulananth/edgartools-platform/pull/657) is open/draft.
A subsequent CI check found the PG16 image prerequisite missing in the
integration job; fix that first. Local 134-test evidence remains valid.

1. Fetch the published integration branch and read tickets 04 and 05 plus this
   evidence. Preserve disabled automatic rules and opt-in consumer behavior.
2. Finish ticket 04's reviewed deferred disposition lifecycle and staged,
   resumable large-component replay/reversal. Add PostgreSQL tests for recovery
   and mandatory completeness; do not relax migration 027's review invariant
   without an audited replacement contract and a new migration. The current
   SQL guard scans retained deferred reviews; bound that validation work before
   qualifying large source volumes.
3. Confirm the prepared three-company candidate (or obtain another approved
   manifest), then activate coverage through the existing governed authority,
   register the exact dataset/policy, apply pending migrations as owner, and
   run a bounded evidence-only ingestion. Review bindings before creating
   master identities. Publish/reconcile all required local contracts under one
   root run. Record actual results; the prepared bundle is not execution proof.
4. Implement GLEIF Level 1, relationships/reporting exceptions and accepted
   OpenCorporates corroboration; prove joint SEC/GLEIF Company binding, field
   policies, lifecycle, complete-publication accounting, reconciliation and
   local consumer parity. Only after the Company completion gate passes,
   connect Person, ADV roles/funds, audit, securities, ownership/13F and other
   approved domains through the shared stage.
5. Finish API/export/graph consumer migration and hosted materialization with
   explicit completeness and idempotent recovery checks. Then qualify the
   identical migrations on the user-selected hosted target when requested.
6. Rehearse catch-up, reconciliation, cutover and rollback before activation.
   Preserve the old MDM for the accepted 30-day window.

The PR is a reviewable development checkpoint. It neither merges itself nor
deploys AWS/Snowflake resources.
