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

**Status:** resolved (2026-08-26) — `mdm check-fence` shipped, live-verified
against prod through the real `application` DSN, and caught a genuine third
instance of the exact gap this ticket exists to monitor for (see the
`source_evidence_conflict` finding below) before this ticket even closed.

- [x] Decide where the check runs and how often — joins the already-
  consolidated `edgartools-<env>-mdm-utility` state machine as a new
  `mdm_check_fence` mode (no bespoke new state machine — the map's "no new
  infrastructure substrate" constraint pointed straight at reusing this),
  triggered by a new off-by-default EventBridge rule
  (`--configure-fence-monitor-schedule`) on `rate(4 hours)`. Sizing
  rationale (no historical rotation-frequency data to size against, since
  the trigger is an out-of-band operation by nature — bounds worst-case
  exposure to within a business day at negligible Fargate cost either way)
  is documented inline in `deploy-aws-application.sh`.
- [x] The check itself: `edgar_warehouse/mdm/fence_monitor.py`'s
  `check_ledger_fence`. One refinement over the sweep as originally
  prototyped — the fenced-table set is discovered live from
  `pg_class`/`pg_roles` (any table owned by a role matching
  `edgartools_acquisition%owner`) rather than a fixed list of 11, so a
  future migration's new owned table is covered automatically. This
  directly mattered: see the `source_evidence_conflict` finding below.
- [x] Credential: confirmed live against real prod (piped directly from
  `edgartools-prod/mdm/postgres_dsn`'s existing secret into the check, the
  ordinary `application` DSN, no elevated credential) — the check runs
  clean end-to-end with zero errors. No new credential provisioned.
- [x] Per-finding alerting: `mdm check-fence` emits `mdm_fence_leak_detected`
  (role/table/privilege) and `mdm_fence_access_gap_detected` (table/role)
  per finding, plus a `mdm_fence_check_result` summary event two CloudWatch
  Logs metric filters read (`--configure-fence-monitor-alarm`), each backing
  its own alarm — mirrors `mdm-ahead-of-silver` ticket 05's
  `remaining_null_count` pattern, including `treat-missing-data=breaching`
  so a schedule that silently stopped firing also alarms.
- [x] Detection only, confirmed by code review — no auto-remediation path
  exists anywhere in the diff.
- [x] Live test: `tests/integration/test_fence_monitor_postgres.py` (Docker,
  real Postgres) creates a real `snowflake_write` role, grants it access,
  confirms detection, revokes, confirms clean — plus a companion test
  proving a table owned by `edgartools_acquisition_owner` but never
  hardcoded anywhere in this module is still discovered and its leak
  caught (the "not fix once" proof), and a third proving the access-gap
  (allow-side) check fires and clears too.

**Two-sided check, not just the deny side (found during implementation, not
originally in this ticket's own text):** a `/gof-refactor-reviewer`-adjacent
advisor consultation before writing code flagged that a monitor checking
only "did `application`/`snowflake_write` regain access" would miss the
inverse failure — a future re-provisioning stripping the *legitimate*
owner's own access (the manifest-pipeline-ownership incident's shape,
documented elsewhere in `CLAUDE.md`, applied to this table set). Added
`OperationalAccessGap`, checking that each fenced table's owning role
retains its own SELECT — empirically confirmed during development that
Postgres does not silently exempt an owner from ACL checks (a `REVOKE`
genuinely strips even the owner's own privilege), making this a real,
non-circular signal rather than a redundant one.

**A genuine third instance of Ticket 30's exact gap, caught by this
ticket's own dynamic table discovery before this ticket closed:** live
verification against prod found `source_evidence_conflict` (migration 015,
Ticket 25's evidence-conflict/repair table — owned by
`edgartools_acquisition_owner`, same as 013's nine tables, but never
hardcoded into this module's fenced-table list) still leaking to both
`application` and `snowflake_write`. 015 had the identical missing
`snowflake_write` REVOKE block 013 had before Ticket 30's fix and 014 had
before this ticket's own fix to it — a third sibling of the same gap,
never independently noticed until the monitor's live-discovery design
surfaced it automatically. Fixed the same way (mirrored block, guarded on
`snowflake_write` existing). Final live state: 10 fenced tables (7 from
013 + `source_evidence_conflict` from 015 + 2 from 014) × both roles ×
SELECT/INSERT/UPDATE/DELETE — zero leaks, zero access gaps, confirmed
through the real `application` DSN.

**Not yet enabled in prod as of this entry:** the schedule and alarms are
committed but off by default, matching `daily_incremental`'s own
introduction convention — enabling them (`--configure-fence-monitor-schedule
enable` / `--configure-fence-monitor-alarm enable`) is a separate, explicit
operator step, not run as part of landing this code. `terraform apply`-ing
the new `fence_monitor_scheduler` IAM role is likewise deferred to the
user's own review.
