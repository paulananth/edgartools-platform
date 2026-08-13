# Confirm `ownership_mdm_gold`'s Intended Scope

Type: task
Status: open
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
