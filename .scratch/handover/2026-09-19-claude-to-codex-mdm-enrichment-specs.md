# Handover — 2026-09-19, Claude → Codex (Clean MDM): enrichment specs and two proposals

## TL;DR

Everything the GLEIF Company loader needs on the *planning* side now exists
on `main`, and per your own `company-completion.md` the build is yours.
This note is the single entry point; it supersedes the two shorter
handovers from earlier today, which it links.

Read, in order:

1. This note (five minutes).
2. [`docs/specs/mdm-enrichment/shared-foundation.md`](../../docs/specs/mdm-enrichment/shared-foundation.md)
   — the shared source-evidence contract every enrichment source uses.
3. [`.scratch/gleif-company-augmentation/spec.md`](../gleif-company-augmentation/spec.md)
   — the Company/GLEIF consumer contract your `company-completion.md`
   steps 2–8 must satisfy.
4. The two proposals, both about your tables, both awaiting your answer:
   [per-family checkpoint key](../clean-mdm-checkpoint-key-proposal/issues/01-write-checkpoint-key-proposal.md)
   and [pre-merge candidate table](../clean-mdm-premerge-staging-proposal/issues/01-write-premerge-staging-proposal.md).

Nothing under `.scratch/clean-mdm/`, `docs/specs/clean-mdm/`, or
`edgar_warehouse/mdm/clean/` was touched by any of this.

## The one directive you need from the operator

Stated by the operator on 2026-09-19, verbatim: *"old MDM will be
decommissioned, do not build anything for the old MDM, clean MDM with
multi source merging is the new MDM."*

Both specs are written under it. There is one MDM and one set of MDM
tables — yours. The specs cite `mdm_v2` tables by name and by the sha256
your `store.py` records in `mdm_v2.migration.checksum`; they never restate
your DDL. `mdm_v2` is treated as your schema name, not as a "v2" the
operator separately approved.

## What the specs decided that touches you

| Decision | Effect on Clean MDM |
| --- | --- |
| Root run is `bookkeeping.pipeline_run` | none — your `023` header already says so |
| No new tables anywhere; a source publication is *derived* from `change_ledger.source_revision` rows sharing `(source_family, source_native_revision)` | none — but note the consumer checks completeness *before* calling `commit_batch`, and records the consumed publication identity inside the batch |
| Two transactions, fixed order, nothing spans databases | none — this is your `recovery.md` "Transaction boundary," adopted verbatim |
| No new Postgres roles; seven business names for existing actors | none — "MDM Committer" is your runtime role via `commit_batch`; "Steward" is the `actor` in a decision body |
| International Organization = `identity.kind = 'international_organization'`, no dedicated table | none — the kind is already in your CHECK constraint |
| GLEIF is ~8 independently checkpointed publication families; a family failing continuity never advances a sibling | **your `checkpoint` table cannot express this** → proposal 1 |
| Tier B/C candidates need Steward review *before* commit, persisted | **nothing persists a candidate today** → proposal 2 |

## The two proposals

**1. Per-family checkpoint key** (`.scratch/clean-mdm-checkpoint-key-proposal/`).
Widen `mdm_v2.checkpoint` from `(consumer)` to
`(consumer, source_family, publication_family)`; add `committed_publication`
and `continuity_proof`; keep your existing expected/advancing fence per key.
Evidence it's your direction, not a change of direction: your `recovery.md`
line 20 already describes the checkpoint as carrying "family/epoch and
source position"; your `source-evidence.md` says "each of the six mappings
has its own publication, cadence, checkpoint and recovery"; and your
`company_source.py` lines 195–199 already work around the narrow key by
minting a fresh consumer string per batch (`expected_checkpoint: 0,
checkpoint: 1`), which makes the table a batch log. Four open questions are
listed there for you. **Why it matters now:** the Company consumer needs
two families (Golden Copy + OpenCorporates), so its release gate 7 cannot
pass on today's DDL. A Golden-Copy-only first slice could.

**2. Pre-merge candidate table** (`.scratch/clean-mdm-premerge-staging-proposal/`).
A persisted, reviewable staging row per source record between identity
matching and `MergeStage.apply()`'s commit, so a Steward can review Tier
B/C candidates across sessions before anything becomes master data. Your
`preview` flag doesn't survive one `apply()` call. Four open questions for
you there too. Until this exists, the Company spec says Steward review
happens through your preview path only.

Both are proposals. Accept, adapt, or decline; a recorded outcome either
way is the foundation's release gate 2. If you decline, both specs stay
coherent — they were written against today's DDL.

## One thing the specs left open that's probably yours to answer

Where do a publication family's **continuity-proof field definitions**
live? The foundation spec found `change_ledger.source_registry_coverage.completeness_policy`
is a text policy *name*, not a field set. The recommended home is your
`mdm_v2.dataset.body` — your `source-evidence.md` already scopes the
dataset contract to "publication key/order rules, time semantics, declared
completeness scope." Marked *Open* in the foundation spec; if you agree,
say so and it closes with no new column anywhere.

## Where the Company contract and your `company-completion.md` meet

Your gate already cites this map's tickets 13, 15, and 16 as accepted
semantics. The consumer spec adds nothing to those; it binds them to
`mdm_v2` and states release gates. Points worth checking against your
steps:

- **Step 2 (pin inputs):** the spec's dataset codes (`gleif.lei`,
  `gleif.relationship`, `gleif.reporting_exception`, `gleif.opencorporates_lei`)
  are the ones *your* `source-evidence.md` proposes. They are not installed
  rows yet; the spec says so.
- **Step 4 (bindings):** only revalidated Adjudicated Seed Links (the 308
  in `research/02-decisions.jsonl`) or deterministic crosswalks may bind.
  Tier B/C are candidates, never links. Name match alone never binds. One
  active binding per side. Your Q11/Q16 stays exactly as accepted.
- **Step 6 (relationships):** `IS_DIRECTLY_CONSOLIDATED_BY` and
  `IS_ULTIMATELY_CONSOLIDATED_BY` are new typed Company→Company edges
  published only when both endpoints are accepted Companies;
  `IS_INTERNATIONAL_BRANCH_OF` and the three Fund types are captured and
  deferred; `HAS_PARENT_COMPANY`/`MANAGES_FUND` are never reused.
  Consolidation is never ownership.
- **Step 7 (updates):** daily 24-hour delta, weekly candidate backstop,
  monthly full reconciliation; the monthly job is the *only* path that may
  business-close by absence.

If you find a mismatch between the consumer spec and your gate, the
disagreement is a defect in one of them. Raise it by a handover note back
(`.scratch/handover/<date>-codex-to-claude-<topic>.md`), not by editing
either file — the same boundary kept on your side.

## What was verified, and what wasn't

Both specs had a documentation review on 2026-09-19: every cited file
exists; cohort counts, consolidation figures, relationship type names,
GLEIF field names, role names, table and column names, and migration
checksums were checked against the repository. Five findings, all applied.
The legacy-decommission re-audit of the parent program's 28 tickets and
the GLEIF map's 16 is done: only program tickets 10/11 and workstreams
02/04/06 named a legacy mechanism, each annotated as superseded by
`identity.kind` + `projection`.

**Not verified:** the foundation's own exit gate — an offline fixture
reproducing identical inventories, state changes, and evidence hashes with
zero domain records published. That's a build, and it's release gate 1.

## Supersedes

- [`2026-09-19-claude-to-codex-mdm-premerge-proposal.md`](2026-09-19-claude-to-codex-mdm-premerge-proposal.md)
- [`2026-09-19-claude-to-codex-mdm-checkpoint-key-proposal.md`](2026-09-19-claude-to-codex-mdm-checkpoint-key-proposal.md)

Both remain valid; this note is the one to start from.

## One thing the operator must do

Your map's "Start here" points at `.scratch/clean-mdm/map.md`, not at
`.scratch/handover/`. This note won't surface on its own; the operator
points your next session at it.
