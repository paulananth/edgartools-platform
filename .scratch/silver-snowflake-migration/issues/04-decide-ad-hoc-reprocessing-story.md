# Decide the Ad-Hoc Reprocessing Story

Type: grilling
Status: resolved
Blocked by: 01

## Question

CLAUDE.md documents silver as "also used for ad-hoc re-processing" by
operators — today that means running Python/DuckDB code directly against
`silver.duckdb`. What replaces that workflow once silver is Snowflake-native
dbt models: `dbt run` with operator-supplied vars/selectors, a Snowflake
worksheet against the landing zone or silver models directly, a thin CLI
wrapper the warehouse package still exposes, or something else? Whatever is
chosen must preserve the same operator capability (re-derive a subset of
silver from bronze without a full pipeline re-run) without silently
regressing it into "only a full `load_history`/`daily_incremental` re-run
can do this now."

## Answer

**Correction to this ticket's own premise:** "ad-hoc re-processing" isn't
one workflow — a live investigation of what operators actually run today
found **five distinct mechanisms** with genuinely different triggers (SEC
availability, bronze availability, operator judgment), not variations on
a theme: `targeted-resync`'s three `--scope-type` modes (reference/cik/
accession), `full-reconcile`'s drift-detect-and-auto-heal, the `--force`
bronze-refetch flag, `parse-ownership-bronze`/`parse-adv-bronze`'s
bronze-only re-merge, and `diagnose-silver-anomalies.py`'s genuinely
manual read-SQL/print-remediation-SQL pattern. Collapsing these into one
generic "reprocess" command would blur exactly the distinctions
CLAUDE.md's own `--force` policy exists to keep explicit. They resolve
into three capability classes, not five, but not one either.

### Class (a): SEC-fetching reprocessing — unaffected by this migration

`targeted-resync`'s `cik`/`accession` scopes, `full-reconcile`'s
auto-heal, and `--force`'s bronze-refetch behavior all operate at the
bronze layer (SEC HTTP calls, artifact download, idempotency
cache-bypass) — none of them touch `silver.duckdb` directly today except
by *triggering* the parser afterward. This migration changes nothing
about how they're invoked or scoped; they stay exactly as they are.

### Class (b): bronze-only re-merge — the operation this migration actually changes

Today's `parse-ownership-bronze`/`parse-adv-bronze` (re-run the form
parser against bytes already in S3, zero SEC calls, scoped by
`--accession-list`/`--limit`/`--lookback-years`) is replaced by a
**CLI command that re-parses bronze and re-runs the same reused
native-pull apparatus (Ticket 01) to push the result into
`EDGARTOOLS_SILVER_LANDING`**, with identical scoping flags. Because
landing is append-only, a re-parse doesn't need a "merge" step at all in
the old sense — it just adds new landing rows with a fresh
`parse_sequence`, and Ticket 01's existing window-function collapse
picks up the corrected/updated version automatically the next time the
silver dynamic tables refresh. This is strictly simpler than today's
`ON CONFLICT DO UPDATE` re-merge logic, not a downgrade of it — the same
simplification Ticket 01 already established for the primary ingest path
applies identically here, since ad-hoc reprocessing and the primary path
now go through the exact same mechanism.

### Class (c): manual diagnosis — same shape, different target and different remediation form

`diagnose-silver-anomalies.py`'s pattern (read-only diagnostic SQL,
*print* remediation SQL for a human to run, never auto-execute) carries
over as-is against Snowflake instead of DuckDB — same shape, no design
change needed for the read/diagnose half. The **remediation** half does
change, and this is worth locking down explicitly since it wasn't asked
directly: today's script prints `UPDATE`/`DELETE` statements, which has
no honest analog once landing is append-only (there's nothing to update
or delete in place). The corrected pattern: the script prints one of two
things depending on the anomaly's source —
1. **A data-derivation bug** (parser produced a wrong value from correct
   bronze bytes) → print the class-(b) re-parse command scoped to the
   affected accessions, not raw SQL.
2. **A genuinely upstream SEC-side anomaly** the parser correctly
   reflects (rare, but real — see CLAUDE.md's "INSTITUTIONAL_HOLDS"
   trailing-newline-drift precedent) → print an `INSERT` adding a
   corrective landing row with a later `parse_sequence`, which the
   existing collapse logic then treats as current — never a raw `UPDATE`/
   `DELETE` against a materialized silver table directly, which would be
   fighting the dynamic table's own refresh instead of working with it.

**Net:** operator capability is fully preserved — every one of today's
five mechanisms has a named, working replacement (three unchanged, one
simplified rather than downgraded, one re-targeted) — and none of them
collapse into "only a full pipeline re-run can do this now," which is the
regression this ticket was explicitly guarding against.
