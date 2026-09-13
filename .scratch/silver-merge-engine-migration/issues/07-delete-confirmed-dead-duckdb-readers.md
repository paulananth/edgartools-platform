# 07 — Delete the confirmed-dead local-DuckDB readers

**Type:** task

## Question

Five modules read a local `SilverDatabase` that is never hydrated, with no scheduled presence
and no other map planning around them (checked 2026-09-13 against `deploy-aws-application.sh`
and every `.scratch/*/` map): `application/commands/validate_data_quality.py` (6 reads),
`application/commands/parse_adv_bronze.py` + `application/adv_bronze_discovery.py`,
`application/relationship_bulk_load.py`, `acquisition/capture_parity.py`. Delete them, same
discipline as duckdb-retirement-cutover Ticket 12: grep every caller first, confirm zero
scheduled presence, delete with their tests, remove CLI/registry entries.

Two to confirm rather than assume: `validate-data-quality` is named by one other map
(large-profile-unscoped-load-audit Ticket 03) — check whether that map still expects it;
`parse-ownership-bronze` IS in the deploy script, so it belongs to
[Ticket 06](06-submissions-and-artifact-tables-landing-only.md)'s reader sweep, not here.

**Blocked by:** none — frontier.
