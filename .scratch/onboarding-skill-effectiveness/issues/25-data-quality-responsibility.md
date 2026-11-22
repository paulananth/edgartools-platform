# data-quality: Define one responsibility

Type: task
Status: resolved
Priority: P0
Blocked by: 01, 07, 13
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-quality](../../../skills/data-quality/SKILL.md)
Step: 1 of 6
Skill dependencies: data-profiling, data-modeling
Applicability: Every source with field constraints, defects or downstream quality obligations.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Translate measured defects and governed requirements into checks, dispositions and quality evidence.

Inventory existing instructions against the neighboring owners: data-onboarding or refining-rules; data-catalog owns the checks' business meaning. Reconcile the current index and references before moving any text.

Start from skills/data-quality/SKILL.md: plan, measure, decide, write, Publish quality meaning to the business catalog. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md); [data-profiling: Define one responsibility](./07-data-profiling-responsibility.md); [data-modeling: Define one responsibility](./13-data-modeling-responsibility.md)

Priority rationale: Measured checks and dispositions prevent unsafe mappings.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] List decisions, inputs and outputs owned here using current repository evidence. Verified against the current Data Quality skill, Data Profiling and Data Modeling ownership tables, Data Onboarding's quality step, Refining Rules' change-quality step, Business Catalog, and Bookkeeping recovery; recorded in [Decisions, artifacts and handoffs](../../../skills/data-quality/SKILL.md#decisions-artifacts-and-handoffs). (2026-11-20 19:43 ET)
- [x] Assign each overlapping responsibility one authoritative owner and a named handoff. Verified by reconciling the skill index and inbound references from profiling, modeling, onboarding, refining-rules and data-catalog with the cited owner sections; the index already routes each activity to its owner. (2026-11-20 19:43 ET)
- [x] Demonstrate the boundary on valid and invalid rows, a deferred identity and a failing check that must survive into stored quality evidence; link retained work rather than duplicating it. The synthetic [MDM receipt recovery scenario](../../../tests/integration/test_mdm_quality_evidence_postgres.py) passed when parent reran it on current `origin/main` (`ba51a974`) from the updated ticket-25 worktree: 1 passed in 4.77s on disposable PG16 (2026-11-22). It verifies check identity/action/counts, deferred-identity separation, receipt privacy and immutable replay after a lost report, Bookkeeping admission, and unchanged full MDM count/digest readback. This qualifies receipt-v1 recovery only for synthetic disposable storage; production enablement remains pending. Keep `mdm.quality.evidence.v1` out of production targets and `MDM_QUALITY_EVIDENCE_V1` unset.
- [x] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. Draft PR #2028's head `9649cc0` passed all 12 CI jobs in run #45052107235, in addition to the D5 disposable PG16 scenario. The ticket-closeout commit creates a new head; keep the PR draft until that head's CI is green. No production enablement is authorized by the recovery test.
- [x] Learning → skill: Data Quality owns check/fix meaning and measured dispositions; onboarding/refining-rules own the lifecycle-specific configuration handoff, Data Catalog owns business definitions, and Bookkeeping owns receipt admission. Recorded in [Decisions, artifacts and handoffs](../../../skills/data-quality/SKILL.md#decisions-artifacts-and-handoffs). (2026-11-20 19:43 ET)

## Answer

Data Quality owns the translation from measured defects and governed
requirements into supported checks, fixes and dispositions, plus the count
evidence used to decide them. Data Profiling owns the measurements and proposed
findings; Data Modeling owns part semantics; Data Onboarding writes new-feed
contracts and configuration; Refining Rules writes live-feed changes; Data
Catalog owns business definitions and native test-case definitions; Bookkeeping
admits durable execution receipts. The skill records this boundary in
[Decisions, artifacts and handoffs](../../../skills/data-quality/SKILL.md#decisions-artifacts-and-handoffs).

The existing [skills index](../../../skills/README.md) already routes each
activity to its skill, so no index entry needed moving or duplication. Existing
inbound references were checked in data-profiling, data-modeling,
data-onboarding, refining-rules and data-catalog. Their terms agree with the
new ownership table.

Boundary trace: static ownership cases plus one executed synthetic D5 recovery qualification on disposable PG16; no provider acquisition or production/shared-store source load.

| Case | Data Quality decision | Retained evidence and handoff |
|---|---|---|
| A record passes its configured checks | Preserve it as a valid result of those checks; a zero failure count is meaningful only after the planner's planted-record check proves each kind can fire | The evaluator's check definitions and counts remain keyed by check id/kind and failure action; [MDM quality tests](../../../tests/mdm/test_quality.py) cover the evaluator contract |
| A required value fails an `exception` check | Set aside the record with `quality_<id>`; it does not stop the run, and later checks for that record are unknown | The Dataset Contract declares the nonblocking reason; `edgar_warehouse/mdm/quality.py` raises it and [MDM execution](../../../edgar_warehouse/mdm/execution.py) carries outcomes. The [Bookkeeping recovery contract](../../../skills/bookkeeping/RECOVERY.md#mdm-quality-evidence-v1) says receipts retain check identity/action and bounded counts |
| An identifier is deferred by its declared identity type | Keep the contract's `invalid_<type>_checksum` reason; do not add a duplicate quality check for the same validation | The Data Quality plan table points to identifier types and `nonblocking_deferred_reasons`; Data Onboarding owns the contract. This is separate from a quality check failure |
| A hierarchy row violates its rule | Keep the row marked in `invalid_rows.jsonl`; record only an evidence-backed fix for steward approval, otherwise `needs_steward` | Data Profiling's proposed row/evidence remains the input; Data Quality records the disposition. The row is not dropped |

These rows establish the ownership boundary; the synthetic D5 recovery
scenario verifies the stored MDM evidence path. Parent reran it on current
`origin/main` (`ba51a974`) from the updated ticket-25 worktree; it passed on
disposable PG16 (1 passed in 4.77s), including check identity/action/counts,
a deferred identity distinct from a failing flagged check, receipt privacy,
immutable replay after a lost Bookkeeping report, unchanged MDM readback, and
Bookkeeping admission.

CI run #45052107235 passed all 12 jobs for PR #2028 head `9649cc0`. Ticket 25
is resolved on that evidence. The closeout-only commit creates a new head and
the PR remains draft until its current-head CI passes. Production target
activation and the `MDM_QUALITY_EVIDENCE_V1` switch remain off pending explicit
operator enablement.

Baseline and provenance: `HEAD` is
`4881e8322909888860db576f65730bc4889dc5a4`. A live `git ls-remote origin
refs/heads/main` returned `2bcbbda62f19b6b8c17c1962a95daa26d38ab828`; its only
changes since this head are the Data Profiling entrypoint and its ticket. The
Data Quality skill blob is identical at both revisions, and current Data
Profiling and Data Modeling sections retain the named handoffs. A fetch could
not update the shared worktree ref because Git could not write
`/Users/aneenaananth/projects/edgartools-platform/.git/worktrees/edgartools-platform-ticket-25/FETCH_HEAD`;
the remote commit object was locally readable with `git show`. The prerequisite
Data Modeling ownership work (`576904f0`, PR #1971) and rules-owner
clarification (`adee4305`, PR #1978) are in this history.
The installed `~/.agents/skills/data-quality` and
`~/.claude/skills/data-quality` links both resolve to the separate checkout
`/Users/aneenaananth/projects/edgartools-platform`; its `data-quality` skill is
at `3884e81` and its last skill-file change is `277b67e` (2026-11-08), so it is
stale relative to this branch and was not used as the edit source. The
installed `write-skill` guidance was read. Its `gstack-skill-bill data-quality`
resolves the installed copy (19,995 bytes), not this worktree's file, so that
size is not reported as this change's size.

Checks: `UV_CACHE_DIR=/private/tmp/uv-cache-ticket25 uv run --no-project
--with pytest -- pytest -q -p no:cacheprovider
tests/unit/test_profiling_genericity.py` — **142 passed**; the first attempt
without `UV_CACHE_DIR` could not create a file in the configured cache outside
the writable workspace. `git diff --check` — **clean**. The genericity check
does not validate ownership or execution behavior.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
