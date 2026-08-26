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

**Status:** resolved (decision made, code/tests shipped; bullet 4's live
prod run is a separate, explicitly-gated operational step — see Answer)

- [x] Confirm definitively whether any deploy path in this repo (ECS task,
  Step Function, bootstrap script, or a documented manual runbook step)
  ever connects to MDM Postgres as anything other than `application` for
  `mdm migrate` — if one exists (e.g. `snowflake_admin` during
  `bootstrap-prod-mdm.sh`'s own provisioning run), document it as the real
  path privileged reruns must use instead.
- [x] If no such path exists today, decide how a privileged rerun of 013 (or
  any future owner-gated acquisition-ledger migration) is meant to reach
  prod at all: options include (a) a one-off manual/admin invocation
  documented as a runbook step (mirroring how `bootstrap-prod-mdm.sh`
  itself is already a manual, admin-run script, not automated CI/CD), (b)
  granting `application` a narrowly-scoped, `SET ROLE`-only (non-inheriting)
  membership in `edgartools_acquisition_owner` specifically for migration
  reruns — note this risks reopening the same "does `SET ROLE` actually
  behave as expected in this Snowflake Postgres environment" question
  Ticket 30 hit and left unresolved, or (c) something else.
- [x] Make `_apply_acquisition_ledger_migration`'s silent-skip outcome loud:
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

## Answer (2026-08-26)

**Bullet 1 — a privileged path already exists, no new one needed.**
`infra/scripts/bootstrap-prod-mdm.sh` already connects to MDM Postgres as
`snowflake_admin`, not `application`, to run `mdm migrate`: it calls `snow
sql -q "ALTER POSTGRES INSTANCE <name> RESET ACCESS FOR
'snowflake_admin';"` (a Snowflake-Postgres-native, one-shot password reset
for exactly that role, independent of `application`'s own separate `RESET
ACCESS FOR 'application'` call later in the same script), builds
`admin_dsn = postgresql://snowflake_admin:<pw>@...`, and runs `MDM_DATABASE_
URL=<admin_dsn> ... edgar-warehouse mdm migrate`. Because `current_user`
during that call is `snowflake_admin` (not `'application'`), migration
013's own role-provisioning block (`IF current_user <> 'application' THEN
GRANT edgartools_acquisition_owner TO %I WITH INHERIT FALSE, SET TRUE ...`)
grants `snowflake_admin` exactly the membership `_apply_acquisition_ledger_
migration`'s `may_manage` gate checks for — so `SET LOCAL ROLE
edgartools_acquisition_owner` and every owner-gated statement after it
succeed. This is confirmed by the script's own inline comments (lines
~284–293) describing this exact grant happening "where %I = current_user =
snowflake_admin during that call."

**Bullet 2 — option (a), already built, nothing new to design.** No new
script or role-grant is needed: re-running `bootstrap-prod-mdm.sh` is the
answer, and the script's own header already documents it as safe to re-run
("Re-running this script is safe (each step is idempotent on the
database/schema side) but always issues fresh Postgres passwords"). Option
(b) (grant `application` a narrow membership) was rejected, matching the
ticket's own flagged risk — migration 013's `IF current_user <>
'application'` guard is a *deliberate* security boundary (the acquisition
ledger's entire role model exists specifically so `application` never gets
owner-level access ambiently), not an oversight; weakening it to make
reruns more convenient would undermine the exact protection Ticket 30 is
trying to add.

**Cost of using this path, so it's not treated as free**: re-running
`bootstrap-prod-mdm.sh` rotates *both* `snowflake_admin` and `application`
Postgres passwords and rewrites both `<prefix>/mdm/postgres_dsn` and (unless
`--skip-snowflake-secret`) `<prefix>/mdm/snowflake` in Secrets Manager. This
is a real, if fully expected and already-relied-upon, production action —
not something to run casually just to check a box. Fine for the (rare)
"a new owner-gated migration needs to reach prod" case this ticket is
about; not something to reach for routinely.

**Bullet 3 — done.** `_apply_acquisition_ledger_migration`,
`_apply_source_registry_migration`, and `_apply_source_evidence_conflict_
migration` (all three share the identical `may_manage`-gated silent-return-
False shape — this gap was never unique to 013) now call a new
`_log_privileged_rerun_skipped(migration_name, owner_role)` helper right
before returning `False`, emitting a `mdm_migration_privileged_rerun_
skipped` JSON event to stderr (same plain `print(json.dumps(...), file=sys.
stderr, flush=True)` convention already used elsewhere in this codebase,
e.g. `pipeline.py`'s `mdm_relationship_skip` events — no new logging
framework introduced). New test,
`tests/integration/test_acquisition_ledger_postgres.py::
test_privileged_rerun_skip_is_logged_not_silent`, calls the real function
against the real Postgres role graph the module's own Docker fixture
already sets up (connecting as `application`, which the fixture's own
migration setup already proves lacks owner membership) and asserts the
event fires with the right `migration`/`owner_role`/`reason` fields. Full
suite: `tests/integration/test_acquisition_ledger_postgres.py` (10 tests),
`test_source_registry_postgres.py`, `test_conflict_postgres.py` (18 total)
all green; `tests/mdm` + `tests/acquisition` (772 tests) unaffected.

**Bullet 4 — not done, needs an explicit live prod run.** This requires
actually executing `bootstrap-prod-mdm.sh` against prod, which rotates real
credentials as described above — a hard-to-reverse, shared-infrastructure
action that needs the user's explicit go-ahead, not something to run
unilaterally while resolving a wayfinder ticket. Once run, it would both
close this bullet AND apply/verify [Ticket 30](30-fence-application-from-acquisition-tables-under-snowflake-write.md)'s
already-merged `snowflake_write` REVOKE fix (bullet 4 of that ticket) in the
same pass — the two tickets' remaining live-verification steps are now the
same action.
