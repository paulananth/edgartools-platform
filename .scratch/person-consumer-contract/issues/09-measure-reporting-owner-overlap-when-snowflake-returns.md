# Measure reporting-owner overlap and person-vs-entity split once Snowflake is reachable

Type: research
Status: open
Blocked by: operator task — restore Snowflake billing (prod warehouses suspended, "free trial has ended", observed 2026-09-19)

## Question

Ticket 01's questions 1 and 3, unmeasurable without
`EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_OWNERSHIP_REPORTING_OWNER`:

1. For each plausible 8-K `(issuer CIK, normalized name)` pair (6,834 in
   research 01), how many reporting-owner rows match on the same issuer
   with a consistent `is_officer`/`is_director` flag — exactly one, more
   than one, none?
2. Of distinct `owner_cik` values, how many are natural persons versus
   entities, by flag combination (`is_ten_percent_owner` without
   officer/director is the usual entity signature)?
3. Of the 398 names seen under multiple issuers, how many resolve to one
   `owner_cik` (one person, several boards) versus several?

Read-only. Record query, run identity, counts, and result-set SHA-256
next to research 01. Refines ticket 02's expected hit rate and feeds
ticket 03's classification rule.
