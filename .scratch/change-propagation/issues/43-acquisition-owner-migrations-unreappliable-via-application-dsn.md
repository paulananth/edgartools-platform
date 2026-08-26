# 43 — Migration 013's owner-gated statements have no live deploy path via the `application` DSN

**What to build:** Confirm and close a deploy-path gap found while investigating
[30 — Fence `application` from acquisition ledger tables under Snowflake Postgres's `snowflake_write` role](30-fence-application-from-acquisition-tables-under-snowflake-write.md):
the only Postgres credential this platform's automation actually uses to run
`mdm migrate` in prod is the `application` role (secret
`<prefix>/mdm/postgres_dsn`, confirmed live by tracing
`edgartools-prod-mdm-utility`'s `mdm_migrate` mode through
`deploy-aws-application.sh` to `MDM_POSTGRES_DSN_SECRET_ARN` →
`MDM_DATABASE_URL`, and independently in `bootstrap-prod-mdm.sh`'s own text:
"populates the two AWS Secrets Manager secrets the warehouse runtime reads
... giving the application role its runtime privileges"). Live, read-only
verification (`pg_has_role('application', 'edgartools_acquisition_owner',
'MEMBER')`) confirms `application` is **not** a member of
`edgartools_acquisition_owner` in any form (not even a non-inheriting one).

`_apply_acquisition_ledger_migration`
(`edgar_warehouse/mdm/migrations/runtime.py`) gates a *rerun* of migration
013 on `may_manage = pg_has_role(current_user, 'edgartools_acquisition_owner',
'MEMBER')`; when `installed and not may_manage`, it returns `False` — a
**silent skip**, not an error. This means: any new owner-gated statement
appended to `013_acquisition_ledger.sql` after its first install (e.g.
Ticket 30's own proposed `REVOKE ALL ... FROM snowflake_write`, if that
option is chosen) will **not run** the next time `mdm migrate` fires in prod
through the standard, only-available deploy path — it will report success
(the surrounding Step Function/ECS task sees exit 0) while doing nothing,
exactly the "false positive" shape already documented in this file's own
"MDM Postgres migration-011 schema drift" CLAUDE.md entry and its sharper
correction.

**Blocked by:** None — can start immediately, but its answer directly gates
how [Ticket 30](30-fence-application-from-acquisition-tables-under-snowflake-write.md)
option (a) can actually be shipped, so resolve alongside or before finishing
that ticket's implementation.

**Status:** ready-for-agent

- [ ] Confirm definitively whether any deploy path in this repo (ECS task,
  Step Function, bootstrap script, or a documented manual runbook step)
  ever connects to MDM Postgres as anything other than `application` for
  `mdm migrate` — if one exists (e.g. `snowflake_admin` during
  `bootstrap-prod-mdm.sh`'s own provisioning run), document it as the real
  path privileged reruns must use instead.
- [ ] If no such path exists today, decide how a privileged rerun of 013 (or
  any future owner-gated acquisition-ledger migration) is meant to reach
  prod at all: options include (a) a one-off manual/admin invocation
  documented as a runbook step (mirroring how `bootstrap-prod-mdm.sh`
  itself is already a manual, admin-run script, not automated CI/CD), (b)
  granting `application` a narrowly-scoped, `SET ROLE`-only (non-inheriting)
  membership in `edgartools_acquisition_owner` specifically for migration
  reruns — note this risks reopening the same "does `SET ROLE` actually
  behave as expected in this Snowflake Postgres environment" question
  Ticket 30 hit and left unresolved, or (c) something else.
- [ ] Make `_apply_acquisition_ledger_migration`'s silent-skip outcome loud:
  at minimum, log a clear warning (not just `return False`) distinguishing
  "already installed, no privileged reruns pending" from "already installed,
  but this connection cannot apply pending owner-gated changes" — the
  current code cannot tell these apart, which is exactly how the migration-011
  false-positive incident went undetected for a day.
- [ ] Verify live: with whatever fix is chosen, confirm a genuinely new
  owner-gated statement appended to 013 (or a placeholder no-op one, if
  none is ready yet) actually executes through the real deploy path.

**Notes:** Surfaced during Ticket 30's live investigation
(2026-08-25/26), not by this ticket's own research — see that ticket's
Answer for the probe experiment that led here.
