# Confirm `ownership_mdm_gold`'s Intended Scope

Type: task
Status: resolved
Blocked by: none

## Question

Is `ownership_mdm_gold` a deliberate, narrower isolation boundary (an
ownership-only composite chain, cheaper and safer to run than the full
`bronze_seed_silver_gold`), or an abandoned prototype superseded by it?

Raised by [Decide the Production Workflow Portfolio](14-decide-the-production-workflow-portfolio.md),
which resolved `bronze_seed_silver_gold` as the sole canonical composite
chain and retired `silver_mdm_gold`/`mdm_gold` outright, but left this one
machine's keep/retire call open: it has exactly one execution (aborted,
2026-07-25, Ticket 13) with no reconstructable Fargate cost and no bound
Snowflake output. Neither the git history nor this map's existing evidence
settles which of the two readings is correct. Resolve via git blame/PR
history on the machine's introduction, or by asking the operator directly.
The answer determines whether this machine joins the retirement list or
gets a distinct, documented scope alongside `bronze_seed_silver_gold`.

## Answer

**Deliberate, narrower isolation boundary — confirmed, not an abandoned
prototype.** Settled unambiguously by the code itself, not inference:

`infra/scripts/deploy-aws-application.sh` (~line 4595) carries its own
design-intent comment directly above the generator: *"ownership_mdm_gold:
Form 3/4/5 already in silver → persons + IS_INSIDER only (Ticket 21).
Companies are NOT re-resolved — they do not change on an insider load. No
full `mdm run --entity-type all`."* The generated ASL's own `Comment`
field states the same thing independently: *"Ticket 21 insider path:
optional parse-ownership-bronze, then PERSON-only MDM resolve +
IS_INSIDER derive (no company re-load), export/sync-graph, gold."*

Traced to its introducing/retargeting commit: `02173c80` — "fix(mdm):
Ticket 21 insider load is person + IS_INSIDER only (#262)"
(2026-07-25T17:32:47-04:00). Full commit message: *"Stop re-resolving
companies on ownership/insider paths. Add `--cik` scoping for person
resolve and IS_INSIDER derive, make load-relationships skip non-ownership
entity phases when only IS_INSIDER/HOLDS are requested, and retarget
`ownership_mdm_gold` to `MdmPersons + MdmIsInsider` instead of `mdm run
all`."* (Note: this "Ticket 21" is a different, earlier workstream's
ticket — not this map's own Ticket 21 — distinct namespace, cited here
only for its commit message content.)

This is a genuine cost/correctness optimization: re-running full company
MDM resolution (`mdm run --entity-type all`) on every insider-only
ownership update is unnecessary and wasteful when companies haven't
changed — `ownership_mdm_gold` exists specifically to skip that. Confirmed
still live and unchanged in current source (same lines, same scope, still
wired into `upsert_state_machine`).

**One data point reconciled, not left as a red flag:** Ticket 13's one
recorded execution (`ownership-mdm-gold-10cik-20260725T204806Z`, aborted,
16:48–17:06 -04:00, 2026-07-25) **predates** the retarget commit's landing
time that same day (17:32:47 -04:00). That execution was exercising an
in-development version of this machine, not the finished, currently-live
design — its abort is not evidence against the current design's
soundness.

**Decision: keep, with a distinct, documented scope alongside
`bronze_seed_silver_gold`** — not added to Ticket 14's retirement list.
This closes the one item Ticket 14 explicitly left open pending this
ticket.
