# 44 — Monitor for `snowflake_write` privilege drift on fenced acquisition tables

**What to build:** A periodic, live check that alerts an operator the moment
`application` or `snowflake_write` regains DML access to any of the 11
acquisition-ledger/registry tables Ticket 30 fenced (the nine
`source_*` tables `013_acquisition_ledger.sql` owns, plus
`source_registry_version`/`source_registry_coverage` from
`014_source_registry.sql`) — closing the monitoring gap Ticket 30's
live deploy left open.

Ticket 30 proved, by direct live reproduction against prod, that
Snowflake-hosted Postgres re-grants `snowflake_write`'s baseline DML access
to these objects as a platform side effect of **any**
`ALTER POSTGRES INSTANCE ... RESET ACCESS FOR '<role>'` call — confirmed for
both `snowflake_admin` and `application`. `bootstrap-prod-mdm.sh` now
re-applies the REVOKE as its own last database-mutating step, so a normal
run of that script leaves the fence closed — but that only protects runs
that go through the script end-to-end. Any other credential rotation
(manual incident response via `snow sql ... RESET ACCESS`, a future script
that rotates these roles some other way, or Snowflake's own platform
maintenance touching the instance) reopens the fence silently, with no
error and no signal anywhere in this repo's observability surface. Today
the only way to know the fence is open is to run the same
`has_table_privilege` sweep by hand, live, against prod — exactly what
Ticket 30's own investigation had to do three times to catch this.

**Blocked by:** None — can start immediately. Surfaced while resolving
[30 — Fence `application` from acquisition ledger tables under Snowflake
Postgres's `snowflake_write`
role](30-fence-application-from-acquisition-tables-under-snowflake-write.md),
which is fully resolved and live; this ticket is the deliberately-deferred
follow-up its own writeup names.

**Status:** ready-for-agent

- [ ] Decide where the check runs and how often — a new lightweight
  scheduled job (mirroring an existing pattern in this repo, e.g. a small
  Step Functions/ECS scheduled task, or a Snowflake task calling out via an
  external function if that's cheaper than provisioning new AWS scheduling)
  is more consistent with this map's "no new infrastructure substrate"
  constraint (see map Notes) than inventing something novel. Size the
  interval against real risk, not a guessed default — see the
  `LOAD_SILVER_LANDING_TASK` credit-burn 5-whys in `CLAUDE.md` for what
  happens when a scheduled check's interval is picked without sizing it
  first.
- [ ] The check itself is exactly the `has_table_privilege` sweep already
  proven live in this session: for both `application` and `snowflake_write`,
  across all 11 fenced objects, across SELECT/INSERT/UPDATE/DELETE — zero
  expected, any `true` is a finding. Reuse the query shape from Ticket 30's
  own verification rather than reinventing it.
- [ ] Decide the credential the check runs as. It needs enough privilege to
  query `has_table_privilege` for arbitrary roles/tables (any authenticated
  role can do this — it's a read-only catalog function, not a privileged
  operation) but must **not** need `snowflake_admin` or any rotation-capable
  credential itself, since provisioning a new privileged credential only to
  watch for privilege drift would be a strange trade. Confirm live whether
  the existing `application` DSN (already available to warehouse/MDM tasks)
  is sufficient to run `has_table_privilege` checks against roles other than
  itself before assuming a new credential is needed.
- [ ] On a finding, alert an operator with which specific role/table/privilege
  combination leaked — not just "drift detected" — mirroring the specificity
  `publication.py`'s existing 5-minute-warning/15-minute-hard-alert SLO
  pattern already established elsewhere in this codebase (see the "graph
  storage" architecture notes in `CLAUDE.md` for that pattern's shape).
- [ ] Do not build a new auto-remediation/auto-REVOKE path on top of this
  check. Detection only — repairing a real finding re-runs
  `bootstrap-prod-mdm.sh` (or the two migration functions directly), the
  same way Ticket 30's own live incident was actually resolved; an automated
  REVOKE firing against prod unattended is a bigger risk than the drift
  itself.
- [ ] A live test: deliberately reopen the fence on a disposable object
  or via a controlled `RESET ACCESS` call in a non-prod-impacting way (if
  one exists) or against a test double, confirm the check fires, then close
  it again and confirm the check clears — proving the check can actually
  detect the exact failure mode Ticket 30 found, not just that it runs
  without erroring.
