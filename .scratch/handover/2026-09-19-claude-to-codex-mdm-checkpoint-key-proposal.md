# Handover — 2026-09-19, Claude → Codex (Clean MDM), #2

## TL;DR

A second design proposal for Clean MDM is ready for your review: widen
`mdm_v2.checkpoint`'s key from `(consumer)` to
**`(consumer, source_family, publication_family)`** and add the consumed
publication identity and continuity proof to the row. Nothing under
`.scratch/clean-mdm/`, `docs/specs/clean-mdm/`, or
`edgar_warehouse/mdm/clean/` was touched — it's a standalone recommendation
on its own map, for you to accept, adapt, or decline.

**Read it here, in order:**

1. [`.scratch/clean-mdm-checkpoint-key-proposal/map.md`](../clean-mdm-checkpoint-key-proposal/map.md)
   — destination and ownership-boundary reasoning.
2. [`.scratch/clean-mdm-checkpoint-key-proposal/issues/01-write-checkpoint-key-proposal.md`](../clean-mdm-checkpoint-key-proposal/issues/01-write-checkpoint-key-proposal.md)
   — the proposal: current DDL and fence, what the shared enrichment
   foundation needs, evidence from your own `recovery.md` /
   `source-evidence.md` / `company_source.py` that this is your stated
   direction, the proposed shape, and four open questions left to you.

## Why this exists

The [MDM Enrichment Shared Foundation](../mdm-enrichment-shared-foundation/map.md)
map (the planning layer under GLEIF and the other external enrichment
sources) resolved all seven of the 2026-09-13 GoF review's open decisions
today. Six of them resolve to *existing* rows and tables — yours in `mdm_v2`
and the acquisition ledger's — with no new schema anywhere. The one thing
the foundation needs that your installed DDL cannot express is a
checkpoint per publication family: GLEIF alone is ~8 independently
checkpointed families, and a family that fails continuity must be
reconciled without advancing its siblings. Your `recovery.md` already
describes the checkpoint as carrying "family/epoch and source position";
the 023 migration lags that. The proposal asks you to close that gap, in
your table, on your function.

Related: the foundation locked that **there is one MDM and one set of MDM
tables — yours.** Its spec will cite `mdm_v2` tables by name and defining
migration and never restate them.

## What this is not

- Not an edit to any of your files, specs, or accepted Q1–Q16 policy.
- Not an implementation — no code, no migration.
- Not a ticket on your own map — folding it in (or declining) is your call.

## Also outstanding from earlier today

The [pre-merge staging proposal](2026-09-19-claude-to-codex-mdm-premerge-proposal.md)
(persisted, reviewable candidate table between matching and
`MergeStage.apply()`) is still awaiting your review. The two proposals are
independent; the foundation treats that candidate table as the "consumer
candidate" record of the GoF boundary, so both being accepted completes the
7-record contract on your side.

## One thing you'll need to do yourself

Your map's "Start here" points at `.scratch/clean-mdm/map.md`, not at
`.scratch/handover/`. The user will need to point you at this note directly
when your next session starts.
