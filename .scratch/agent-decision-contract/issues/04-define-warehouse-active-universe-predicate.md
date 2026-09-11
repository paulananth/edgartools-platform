# Define the warehouse-active predicate for Decision Subject Universe

Type: grilling
Status: resolved
Blocked by: 01

## Question

The map locked Decision Subject Universe as warehouse-active ∩ MDM-active.
Current feature-screen SQL uses only `MDM_COMPANY_ENTITY.tracking_status =
'active'`. What is the warehouse-active predicate?

Decide:

1. Which table and column(s) mean warehouse-active (gold `COMPANY`,
   bookkeeping sync state, seed tracking, or something else).
2. How the intersection is expressed in the contract view.
3. What happens when MDM-active and warehouse-active disagree for a CIK
   (exclude, flag unavailable, or fail the watermark).

Predecessor: [Universe single-writer](../../agent-decision-data-plane/issues/14-universe-single-writer.md)
is closed; this ticket names the live predicate, it does not reopen dual
ticker clients.

## Comments

- Q1 (2026-09-10): warehouse-active is Bookkeeping `sec_company_sync_state.tracking_status = 'active'`. Not `bootstrap_pending`. Not gold `COMPANY.TRACKING_STATUS` (MDM). Not silver `sec_company` existence.
- Q2 (2026-09-10): intersection is a **watermark-aligned universe snapshot** written into `EDGARTOOLS_DECISION` at READY publication. Agent views join that snapshot. Bookkeeping is not queried by agents. Not a live join, not Python-only, not federated Postgres.
- Q3 (2026-09-10): one-sided CIKs are **excluded** from the universe. Empty intersection ⇒ **not READY**. Operator counts of warehouse-only / MDM-only may live in publication notes, not as agent rows.

## Answer

Warehouse-active is Bookkeeping `sec_company_sync_state.tracking_status = 'active'` (not `bootstrap_pending`, not gold `COMPANY.TRACKING_STATUS`, not silver `sec_company` existence).

The Decision Subject Universe is warehouse-active ∩ MDM-active, published as a **watermark-aligned snapshot** in `EDGARTOOLS_DECISION` at READY publication. Agent views join that snapshot; they do not query bookkeeping.

A CIK on only one side of the intersection is excluded (not listed as `unavailable`). If the intersection is empty, the publication is **not READY**. Gold, Explore, and MDM keep running.

Who writes the snapshot is [Decide who writes a READY Decision Contract publication](06-decide-publication-ready-writer.md).
