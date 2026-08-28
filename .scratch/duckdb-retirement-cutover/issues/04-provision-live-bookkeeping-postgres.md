# 04 — Provision the Bookkeeping Postgres Instance in Live Prod

**Split from the original Ticket 02 during implementation (2026-08-28)** —
see [Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md)'s own
split note. This is the live, hard-to-reverse infra step, deliberately last:
run [Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md)'s
provisioning script against real prod Snowflake, only after
[Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)'s code is
tested and reviewed — not before. This matches the order every "applied
live to prod" entry in CLAUDE.md's history follows: script written and
tested first, live execution as its own confirmed, later action.

**What to build:**

- Run a read-only connectivity check against the target Snowflake account
  first, before any DDL statement — confirm you're talking to the current
  live account (`PRJEDJU-QJB05385` as of this writing, per `snow connection
  list`'s `edgartools-prod` entry; re-verify this hasn't changed rather
  than trusting this ticket's own stale value).
- Execute [Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md)'s
  provisioning script against live prod.
- **Verify grants with a live `has_table_privilege` sweep run *after* the
  script's actual last step** — not just after the DDL statements. CLAUDE.md
  documents that this platform re-grants `snowflake_write`'s baseline DML
  access as a side effect of rotating *either* `application`'s or
  `snowflake_admin`'s credentials, and a prior `bootstrap-prod-mdm.sh` run
  silently reopened an identical fence this same way. If this script's own
  last step touches either credential, the sweep must run after that step,
  not before it.
- Check whether `mdm check-fence` (`edgar_warehouse/mdm/fence_monitor.py`)
  discovers these new tables automatically (it discovers live from
  `pg_class`/`pg_roles`) — if it doesn't, because of the owner role this
  script chose, note that gap explicitly rather than assuming coverage.
- Confirm the new store starts empty as expected (no accidental data
  carried over), and that [Ticket 02](
  02-move-bookkeeping-tables-to-snowflake-postgres.md)'s empty-start
  behavior (every CIK reverts to pending) is now genuinely in effect —
  this is the point where that operator-accepted cost actually lands, not
  a hypothetical anymore.

**Blocked by:** [Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md),
[Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)

**Status:** blocked

- [ ] Read-only connectivity check against the live target account passes
      before any DDL runs
- [ ] Provisioning script executed against live prod Snowflake; all 11
      tables exist, additive grants applied
- [ ] `has_table_privilege` sweep run after the script's actual last step
      (not just after DDL) confirms no unintended `snowflake_write` access
      was re-granted
- [ ] `mdm check-fence` coverage of the new tables is confirmed or its gap
      documented explicitly
- [ ] A real end-to-end smoke test (e.g. a lease acquire/release cycle, a
      checkpoint read/write) against the live new store succeeds
- [ ] Empty-start behavior confirmed live, and the deploy runbook note from
      Ticket 02 is cross-checked against what actually happened
