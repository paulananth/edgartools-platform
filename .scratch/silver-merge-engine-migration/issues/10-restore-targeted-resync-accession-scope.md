# 10 — Restore targeted-resync accession scope

**Type:** task (verify live), then a decision

**Status:** open

## Question

`targeted-resync --scope accession` appears broken since duckdb-retirement-cutover Ticket 10
stopped hydrating local DuckDB. `_run_accession_resync` (`warehouse_orchestrator.py`) starts
with `db.get_filing(accession_number)` on a store the command opened empty in a fresh
container, so it should always raise "Unknown accession_number for targeted resync". Found
while grilling [Ticket 06d](06-submissions-and-artifact-tables-landing-only.md); a code
reading, not yet confirmed by a run.

1. **Verify live:** run one accession-scoped `targeted_resync` in prod against a known
   accession and capture the result. If it works, record why the code reading was wrong and
   close this ticket.
2. **If it is broken, decide the fix:**
   - read the filing row from Snowflake silver (`SnowflakeSilverReader`), then continue with
     the same-run artifact/text/parse steps; or
   - capture the accession's CIK submissions first (as the `cik` scope already does), so the
     in-run lookup 06d introduces holds the filing.

   The second reuses the existing capture path and costs one submissions fetch; the first
   adds a Snowflake read but keeps the scope narrow.

Not part of 06d: the in-run lookup answers "what did this run already record", and this
command's read is for a filing recorded by an earlier run.

**Blocked by:** none — frontier. The second fix option depends on 06d's in-run lookup landing.
