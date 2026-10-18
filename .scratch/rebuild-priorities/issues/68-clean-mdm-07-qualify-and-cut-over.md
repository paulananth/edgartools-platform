# Qualify Snowflake Postgres and rehearse cutover

Priority: 68, tier 5, needs SEC requests or AWS. Map: [Rebuild priorities](../map.md). Moved from `.scratch/clean-mdm/issues/07-qualify-and-cut-over.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task
Status: open, later: the hosted Snowflake Postgres cut-over is under Not yet specified in `mastering-to-done/map.md` (2026-10-02 audit, mastering to-do 01).
Was: open
Owner: Codex
Blocked by: 21

## Work

Use same migrations on an isolated target after local acceptance. Pin approved inputs; rehearse catch-up, consumer reconciliation and rollback. Set live target and retention details before activation; retain legacy MDM.

## Evidence

On 2026-09-19 the user selected local PostgreSQL for continued qualification
and 30 days of legacy retention after cutover. Snowflake qualification is
deferred. The user asked for an explanation of pinned inputs; the inherited
three-company local landing bundle is being inspected as a candidate.
Source/consumer integration gates must finish before any consumer cutover.

## Checklist

- [ ] Run `mdm migrate` on the hosted store once it exists: it carries every migration the local store has, including 005–007 (ticket 18) and 010 (ticket 19), moved here 2026-10-18 12:25 ET
- [ ] Learning → skill
