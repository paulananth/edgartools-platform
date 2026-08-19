# Estimate Snowflake Compute Cost for Native Silver

Type: research
Status: resolved
Blocked by: none

## Question

Phase 1's [Design the Snowflake-Native Silver Layer's Model Structure](01-design-snowflake-native-silver-model-structure.md)
locked the shape: uniformly `dynamic_table` silver models (current-state,
window-function collapse over `EDGARTOOLS_SILVER_LANDING`'s append-only
rows), refreshed on their own `TARGET_LAG` — the same mechanism the 20
existing `EDGARTOOLS_GOLD` dynamic tables already use. Today this
transformation work runs as ~free local DuckDB CPU inside an already-paid-for
ECS task; moving it to Snowflake makes it billed warehouse compute for the
first time. This ticket produces a real cost estimate, not a placeholder,
before Ticket 09/10 lock a cutover order that commits to spending it.

Ground this in real, already-gathered evidence rather than re-deriving from
scratch:

1. **Existing gold dynamic-table cost as a real analog.** The 20
   `EDGARTOOLS_GOLD` tables already run on `TARGET_LAG`-driven refresh
   against a known warehouse (`EDGARTOOLS_PROD_REFRESH_WH`, referenced
   throughout CLAUDE.md's "ecs-cost-sizing" credit-consumption findings —
   e.g. the 6-hour manifest-poll widening was chosen specifically to avoid
   burning ~67 credits/week on a warehouse that couldn't fully suspend).
   Pull real credit-consumption numbers for that warehouse via
   `SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY WHERE
   warehouse_name = 'EDGARTOOLS_PROD_REFRESH_WH'` (or the account's actual
   refresh warehouse name — confirm from `profiles.yml`/Terraform) over a
   representative recent window, and use it as the per-dynamic-table cost
   baseline silver's ~30 models would add to.
2. **`ecs-cost-sizing`'s workflow-unit-economics research** (referenced in
   this session's task history —
   `.scratch/ecs-cost-sizing/research/workflow-unit-economics-2026-08-12.md`
   if it exists, or the map's other tickets) may already have Fargate
   vCPU-second/GB-second rates and a cost-attribution methodology that
   transfers directly to estimating the *removed* DuckDB compute cost this
   migration saves — use it as the "cost saved" side of the comparison, not
   just the "cost added" side.
3. **Data volume.** Query real row counts for the silver-landing tables
   (`EDGARTOOLS_SILVER_LANDING`, 30 tables) and the shards they'd replace
   (`sec_thirteenf_holding` alone is ~6.8M rows per CLAUDE.md) to size what
   a `dynamic_table` refresh over that volume actually costs, not a
   hand-wavy "small" assumption.
4. **Refresh cadence sensitivity.** Since `TARGET_LAG` is the main cost
   lever (tighter lag = more frequent refresh = more credits, matching the
   exact 1-minute-vs-6-hour tradeoff CLAUDE.md's manifest-task incident
   already lived through for gold), give the estimate as a small table
   across 2-3 plausible `TARGET_LAG` settings (e.g. 15 min / 1 hour / 6
   hour) rather than a single number, so Ticket 10 can pick a rollback
   window without re-doing this research.

Write findings to
`.scratch/silver-snowflake-migration/research/compute-cost-estimate-<date>.md`
per this repo's research-skill convention, then post a resolution comment
here linking it and record the answer.

## Answer

Full findings:
[compute-cost-estimate-2026-08-18.md](../research/compute-cost-estimate-2026-08-18.md).

**A real number could not be produced for Directions 1 and 3** — not because
the research was insufficient, but because the live Snowflake account
(`PRJEDJU-QJB05385`, `AWS_US_WEST_2`) was rebuilt from scratch on
2026-08-17/18, one day before this research ran. Every table in
`EDGARTOOLS_SILVER_LANDING`/`EDGARTOOLS_SILVER`/`EDGARTOOLS_GOLD` has 0
rows; `WAREHOUSE_METERING_HISTORY` has exactly 3 rows, ever, for the
refresh warehouse (0.166 credits total, all from today's initial `dbt run`
deploy against empty tables). CLAUDE.md's cited `sec_thirteenf_holding`
~6.8M-row figure is from a prior account incarnation and could not be
re-verified live.

**More significant than the missing number: this research surfaced that
Phase 1's own "built and applied live to prod" claims (Tickets 05/07) do
not hold on the current account.** `LOAD_SILVER_LANDING_TASK` — the
scheduled `COPY INTO` task Ticket 07 built and verified live — does not
exist on `PRJEDJU-QJB05385` at all; its bootstrap SQL
(`infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql`) was never
re-applied after the account rebuild. This is why nothing has ever
refreshed on a schedule in this account (0 of 87 lifetime refreshes have
`refresh_trigger = 'SCHEDULED'` — all are `CREATION`-triggered from the
dbt deploy pass itself). The 30 silver dynamic tables Ticket 01 designed
**are** deployed and correctly shaped (confirmed via `GET_DDL`), and
Snowflake has already determined real refresh-mode splits for them (24
INCREMENTAL / 6 FULL, the 6 being exactly the join-containing ownership/
financial tables found via `grep -il join`) — but nothing is feeding them.

**Also surfaced, independent of this ticket but urgent**:
`SNOWFLAKE_RUN_MANIFEST_TASK` is live at `schedule: 1 MINUTE` on this
account (`created_by_user: ANANP11`, created during the same rebuild),
not the 6-hour value both the Terraform module and CLAUDE.md's own
documented incident say it should be — a live, currently-accruing cost
regression on the exact warehouse silver's new tables would also share.

**Cost estimate delivered, explicitly bounded**: a bottom-up
auto-suspend-floor model, using confirmed live pricing ($2.00/credit,
X-Small = 1 credit/hr, 60s auto-suspend) and confirmed billing mechanics,
gives a floor of **≈$4/month (6hr lag) to ≈$96/month (15min lag)** for the
30 silver tables — before the unmeasured, plausibly-dominant marginal cost
of the 6 FULL-mode tables re-scanning their full landing table on every
refresh at real full-universe volume (explicitly flagged as the single
biggest open unknown). The Fargate-side "savings" this migration nets
against is separately measured at ~$0.02–0.20/month — structurally
negligible; the real trade is architecture/correctness benefit for new,
additive Snowflake spend, not a wash against reduced AWS spend.

**Recommended before Ticket 09/10 fully trust a number**: reprovision
`LOAD_SILVER_LANDING_TASK` on this account (see new Ticket 11), then load
one realistic ownership batch and measure one real `FULL`-mode refresh's
actual cost — that single real data point would replace this ticket's
bounding-logic model with a measured one.
