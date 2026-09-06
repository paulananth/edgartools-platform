Type: task
Status: resolved (2026-09-06)

**Spawned by:** [Ticket 09 — Retire superseded document-loading machines](09-retire-superseded-document-loading-machines.md), noted out of that ticket's own scope: `edgartools-prod-mdm-gold` is a live AWS orphan — confirmed zero executions and zero remaining code references (its writer function and dispatch were already removed by an earlier ticket), but the deployed AWS state machine object itself was never deleted.

## Question

Not a decision — mechanical cleanup, mirroring the rollback-snapshot-then-explicit-delete pattern already established by tickets 03/04/05/06/09 in this same map.

1. Capture a rollback snapshot of `edgartools-prod-mdm-gold`'s current deployed definition (`aws stepfunctions describe-state-machine --query definition`), saved under this map's `rollback-snapshots/`.
2. Confirm zero running/recently-completed executions immediately before deletion (fresh `list-executions` check, not stale evidence from Ticket 09's investigation).
3. Confirm zero code references anywhere in the repo (writer function, dispatch, CLAUDE.md/CONTEXT.md mentions) — Ticket 09's own note says this is already true, re-verify rather than assume.
4. Delete the live AWS state machine object.
5. Update CLAUDE.md/CONTEXT.md if either still lists `mdm_gold`/`edgartools-prod-mdm-gold` as a live object anywhere (the map's own Notes section already documents `mdm_gold` as "deleted outright" per Ticket 07 — confirm that refers to code only and this ticket closes the remaining AWS-object gap).

**Done when:** `edgartools-prod-mdm-gold` is gone from `aws stepfunctions list-state-machines` and a rollback snapshot is on file.

## Answer

Deleted live, 2026-09-06: rollback snapshot captured
(`.scratch/state-machine-consolidation/rollback-snapshots/mdm-gold-pre-delete-2026-09-06.json`),
a fresh `list-executions` check reconfirmed zero executions ever (not just
Ticket 09's earlier evidence), zero live code references reconfirmed (every
`mdm_gold`-substring hit in the repo is either the unrelated
`write_warehouse_mdm_gold_definition` function or an already-retired
sibling), `edgartools-prod-mdm-gold` deleted (`DELETING` -> gone), and
CONTEXT.md's MDM Pipeline Machine `_Avoid_` note updated to reflect the
cleanup instead of flagging it as outstanding.
