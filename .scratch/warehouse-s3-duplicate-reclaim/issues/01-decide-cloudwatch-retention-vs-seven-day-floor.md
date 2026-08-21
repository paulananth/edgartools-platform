# Keep, drop, or rewrite the three-day CloudWatch retention requirement?

Type: grilling
Status: resolved
Blocked by: none

## Question

GSD v1.0 requirement CW-01 says platform CloudWatch log groups retain **3
days** and logs older than 3 days are deleted.

[Production Observability and Image Cost Control](../../ops-cost-control/map.md)
already made seven-day retention durable (ticket “Make Seven-Day Production
Log Retention Durable”), and that map’s Out of scope says: reducing log
retention **below seven days** is out of that effort because durable
evidence must carry longer-lived facts.

Decide for *this* destination:

1. Drop CW-01 from warehouse-s3-duplicate-reclaim (CloudWatch stays at 7
   days; GSD Phase 5 is out of this map).
2. Override the seven-day floor to 3 days, and record why ops-cost-control’s
   forensic window no longer holds.
3. Keep 7-day CloudWatch in prod and treat “3 days” as a different
   (non-prod / named) log class — specify which groups.

Do not change live retention while resolving this ticket.

## Answer

**Option 1.** Drop CW-01 from this destination. Prod CloudWatch stays at the
seven-day Operational Forensics Window locked by [Make Seven-Day Production
Log Retention Durable](../../ops-cost-control/issues/03-make-seven-day-log-retention-durable.md).
GSD Phase 5 (3-day retention) is out of this map.

Why not 2 or 3: shortening below seven days is already out of scope on
[Production Observability and Image Cost Control](../../ops-cost-control/map.md)
because durable evidence must carry longer-lived facts. The reclaim spec
already said “Do not change CloudWatch retention.” A named 3-day class was
not defined and would split operator forensics.

Live read (2026-08-21, no policy change): all three `edgartools-prod`
groups remain `retentionInDays=7`:
`/aws/ecs/edgartools-prod-warehouse`,
`/aws/states/edgartools-prod-warehouse`,
`/aws/ecs/containerinsights/edgartools-prod-warehouse/performance`.

Architecture tests still require seven days (`OPERATIONAL_FORENSICS_WINDOW_DAYS = 7`).
