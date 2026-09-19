# Handover — 2026-09-19, Claude → Codex (Clean MDM)

## TL;DR

A design proposal for Clean MDM's Merge Stage is ready for your review: a
**persisted, reviewable pre-merge staging table**, sitting between identity
matching and `MergeStage.apply()`'s atomic commit. Nothing under
`.scratch/clean-mdm/`, `docs/specs/clean-mdm/`, or
`edgar_warehouse/mdm/clean/` was touched to produce it — it's a standalone
recommendation on its own map, for you to accept, adapt, or decline.

**Read it here, in order:**

1. [`.scratch/clean-mdm-premerge-staging-proposal/map.md`](../clean-mdm-premerge-staging-proposal/map.md)
   — destination and the ownership-boundary reasoning for why this is a
   separate map instead of a ticket on your own.
2. [`.scratch/clean-mdm-premerge-staging-proposal/issues/01-write-premerge-staging-proposal.md`](../clean-mdm-premerge-staging-proposal/issues/01-write-premerge-staging-proposal.md)
   — the actual proposal: a table comparing your Merge Stage against legacy
   MDM's pattern, the exact atomic-transaction constraint (`merge-stage.md:24-29`)
   any staging addition must respect, the staging-table design sketch, and
   four open design questions left entirely to you.

## Why this exists

Investigating the Agent Open Query Surface's Postgres backend
(`.scratch/agent-open-query-interface/`) required tracing MDM's actual
Postgres call sequence end to end — see
[`research/06-mdm-postgres-call-sequence.md`](../agent-open-query-interface/research/06-mdm-postgres-call-sequence.md)
for the full primary-source trace (every claim cites `file:line` against
`edgar_warehouse/mdm/`). Comparing that against your `merge.py`/
`merge-stage.md` design (read live off `origin/codex/clean-mdm-integration`)
surfaced one structural gap worth flagging: your Merge Stage fuses identity
matching, conflict detection, and field selection into one atomic
transaction by explicit design, with nothing persisted that a steward can
review asynchronously before commit — unlike legacy's
`mdm_entity_attribute_stage`. The proposal is the writeup of that gap plus
one concrete way to close it.

## What this is not

- Not an edit to any of your files, specs, or accepted policy (Q1-Q16 stays
  exactly as accepted 2026-09-18).
- Not an implementation — no code, no migrations, no schema changes.
- Not a ticket on your own map — folding it in (or declining it) is your
  call, not decided here.

## One thing you'll need to do yourself

Your map's own "Start here" points at `.scratch/clean-mdm/map.md` and its
numbered issues, not at `.scratch/handover/`. This note won't surface
automatically in your next session — the user will need to point you at it
directly (or at `.scratch/clean-mdm-premerge-staging-proposal/` itself) when
that session starts.

Landed on `main` via PR #658 (`cee23b11`), merged 2026-09-19. This handover
note is on `claude/agent-open-query-interface`, not yet merged as of writing.
