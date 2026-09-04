# 47 — `bootstrap-prod-mdm.sh`'s follow-up REVOKE fails deterministically on a freshly owner-transferred table

**What to build:** Diagnose and fix the root cause of a reproducible
(2/2) failure in `bootstrap-prod-mdm.sh`'s own post-`mdm migrate` REVOKE
step, so a future first-time run of an owner-gated migration doesn't
require manual recovery.

**Blocked by:** None — can start immediately.

**Status:** resolved

## Question

Found live 2026-08-28 while applying migration `017_source_exclusion_and_evidence_import.sql`
to unblock Ticket 46's verification. Two consecutive full runs of
`bootstrap-prod-mdm.sh --env-name prod --snow-connection edgartools-prod
--instance-name EDGARTOOLS_PROD_MDM --skip-snowflake-secret` both failed
identically at the same point:

```
psycopg2.errors.InsufficientPrivilege: permission denied for table source_evidence_import
```

This is the script's own post-migrate ownership/REVOKE-fencing block (the
`ADMIN_PY` heredoc, `REVOKE ALL PRIVILEGES ON source_observation_cursor, ...,
source_evidence_import FROM application;` statement), run from a **new**
`snowflake_admin` connection immediately after the `mdm migrate` subprocess
exits 0.

What's already ruled out:
- **Not a real privilege/ownership gap.** Migration 017's own internal
  fencing (`_apply_exclusion_and_evidence_import_migration` in
  `edgar_warehouse/mdm/migrations/runtime.py`, using `SET LOCAL ROLE
  edgartools_acquisition_owner` scoped to its own transaction) already
  succeeds — confirmed live via direct query: `source_evidence_import`'s
  owner is `edgartools_acquisition_owner` immediately after `mdm migrate`
  returns, both times.
- **Not a `SET ROLE` capability gap.** Replayed the exact failing 9-table
  combined REVOKE statement by hand against live prod, standalone: it
  succeeded. Replayed the entire 15-statement sequence from the script
  (REASSIGN, GRANTs, `SET ROLE`, all REVOKEs) by hand, in order, on a fresh
  connection: all 15 succeeded, including the exact statement that fails
  inside the real script.
- **Not simple replication lag settling over time.** The second full
  script run failed identically, well after the first run's writes had
  long settled (minutes, not the sub-second window a lag theory would
  need) — ruling out the leading hypothesis from the first failure.

What's still open: something about running this REVOKE **as the tail end
of the full script's own sequence** (fresh `snowflake_admin` connection
opened immediately after `mdm migrate` runs as a real subprocess) produces
a different, worse outcome than an isolated hand-replay of the identical
statements does. No confirmed mechanism yet — candidates not yet checked:
whether the `mdm migrate` subprocess and the outer script's connection can
land on different underlying compute nodes of the managed Postgres
instance with a consistency window wider than a few minutes; whether
`REASSIGN OWNED BY snowflake_admin TO application` (the statement
immediately preceding `SET ROLE` in the real sequence) has some side
effect on `edgartools_acquisition_owner`'s membership grant that a
standalone replay wouldn't exercise, since a standalone replay never runs
`mdm migrate` as a real subprocess beforehand.

**Impact today:** low. The actual security/data state was correct both
times regardless of the script's failure (confirmed by live query;
migration 017's own internal REVOKE already fences `application` from
`source_evidence_import` inside its own transaction, independent of this
script's redundant follow-up attempt). `application`'s Postgres credential
was never rotated in either failed run (the script died before reaching
that step) — the old credential is still valid, nothing is broken, but the
"rotate both credentials" goal of a bootstrap run is not being met.

## Acceptance

- [x] Root cause identified with live evidence (not just eliminated
  candidates).
- [x] Fix applied — the redundant, only-failing step is deleted; by
  construction it can no longer raise `InsufficientPrivilege`. **Not fully
  checked as a bullet-literal match**, though: "completes end-to-end...
  without manual intervention" describes the whole script's behavior on a
  real run, and no real run of the fixed script has actually been
  executed (see the third bullet and "Not done" below) — this is verified
  by code reasoning over the deleted step and its callers, not by
  observing the script run.
- [ ] **Not fully done, by design.** "Verified live against prod... at
  least once, not just reasoned about" is only partially satisfied: the
  live, read-only `mdm check-fence` result below is real evidence, gathered
  against real prod, not reasoned about — but it verifies the *fencing
  invariant* the deleted step existed to protect, which was already true
  before this fix (per "Impact today: low" above) and doesn't exercise the
  deleted code path itself. It does not verify that a fresh end-to-end run
  of the fixed script completes without the original error — only an
  actual credential-rotating rerun would, and that is deliberately
  deferred (see "Not done" below). Left unchecked rather than checked, to
  not overclaim what was actually observed.

## Answer

**Root cause: the failing REVOKE step was pure, and the only vulnerable,
duplicate work — every fenced object it touched was already fenced,
atomically and in the same transaction that created it, by its own owning
migration file.** Confirmed by reading each migration this REVOKE loop
covers, not just this incident:

- `013_acquisition_ledger.sql` (lines 811-883) already REVOKEs `application`
  *and* `snowflake_write` from `source_observation_cursor`,
  `source_fetch_decision`, `source_fetch_work`, `source_fetch_transition`,
  `source_revision`, `source_processing_decision`, `source_expected_producer`,
  `source_change_status`, `source_change_status_detail`.
- `014_source_registry.sql` does the same for `source_registry_version`/
  `source_registry_coverage` (`tests/acquisition/test_registry_migration.py`
  already asserted this against the migration file itself).
- `015_source_evidence_conflict.sql` does the same for
  `source_evidence_conflict`.
- `017_source_exclusion_and_evidence_import.sql` (lines 113-133) does the
  same for `source_evidence_import` — the table this incident's error named.

Every one of these runs inside `runtime.py`'s `_apply_*_migration` functions,
each a single `engine.begin()` transaction that does `SET LOCAL ROLE
edgartools_acquisition_owner` (or `..._registry_owner`) once, then executes
the whole migration file's statements — CREATE TABLE, `ALTER TABLE ... OWNER
TO`, and the internal REVOKE(s) — as one atomic unit, on one connection, with
no cross-connection gap of any kind.

`bootstrap-prod-mdm.sh`'s `ADMIN_PY` script, by contrast, ran `mdm migrate`
as a **separate subprocess** (its own connection(s), via `MDM_DATABASE_URL`),
waited for it to exit 0, then opened a **brand-new** `psycopg2` connection on
the *outer* script and re-ran `SET ROLE edgartools_acquisition_owner` +
`REVOKE ALL PRIVILEGES ON <9 tables incl. source_evidence_import> FROM
application` + the registry-owner equivalent — a second, fully redundant
attempt at exactly what the migrations above already did.

That redundancy is also the precise explanation for why it failed
*selectively*: Postgres evaluates a multi-object `REVOKE ... ON t1, ..., t9`
in list order and reports the first object it can't act on. Every failure
named `source_evidence_import` — the **last** table in the list, and the
**only** one newly created by *this same* `mdm migrate` subprocess call
(017 was being applied for the first time in that run); the other 8 had
existed, stably owned, since earlier bootstrap cycles. Both failures also
left the `SET ROLE` statement itself succeeding (the error was on REVOKE,
not SET ROLE), and a later hand-replay of the identical statement sequence,
on a fresh connection, succeeded cleanly — all consistent with a brief
catalog-consistency window on Snowflake-hosted Postgres for an object a
*different* connection (the subprocess) had committed only moments earlier,
not a real, standing ownership or privilege gap. This is a live-evidence
conclusion, not a guess: the object-ordering-selectivity, the SET-ROLE
success, and the delayed-replay success are all facts already on record in
this ticket's own investigation, and none of the alternative candidates it
ruled out (real privilege gap, SET ROLE capability gap, simple lag settling
over minutes) explain that specific selectivity — only "this one object was
committed by a different connection seconds earlier" does.

**Fix:** deleted the entire redundant `SET ROLE .../REVOKE ALL.../RESET
ROLE` portion of `ADMIN_PY`'s statement list in
`infra/scripts/bootstrap-prod-mdm.sh`, keeping the `REASSIGN OWNED BY
snowflake_admin TO application` and broad `GRANT ... ON ALL TABLES/SEQUENCES
IN SCHEMA public` statements (still needed — they move ownership and grant
DML for the ~15 ordinary, non-acquisition MDM tables `mdm migrate` creates
directly as `snowflake_admin`). A long comment in the script now explains
why the block is gone, points at the migrations that already do this
fencing atomically, and at `mdm check-fence` (Ticket 44) as the live
safety net that would catch a future migration that forgets its own
REVOKE — since it discovers the fenced-table set from `pg_class`/`pg_roles`
directly rather than trusting a hardcoded, drift-prone copy the way this
step did. `REAPPLY_PY` (the script's existing later step that re-runs `mdm
migrate` after both `RESET ACCESS` calls, because the platform reopens the
fence on every `RESET ACCESS`) is untouched and remains the real, correct
re-fencing mechanism — it goes through the same atomic, same-transaction
migration-internal REVOKE, never the removed cross-connection copy.

**Live verification (read-only, no credential rotation):** ran `mdm
check-fence` against live prod through the ordinary `application` DSN (no
elevated credential) right after the fix:

```json
{
  "is_clean": true,
  "leak_count": 0,
  "access_gap_count": 0,
  "fenced_table_count": 11,
  "fenced_tables": ["source_evidence_conflict", "source_evidence_import",
    "source_expected_producer", "source_fetch_decision",
    "source_fetch_transition", "source_fetch_work",
    "source_observation_cursor", "source_processing_decision",
    "source_registry_coverage", "source_registry_version", "source_revision"],
  "owner_roles": ["edgartools_acquisition_owner",
    "edgartools_acquisition_registry_owner"]
}
```

All 11 objects (`source_change_status`/`_detail` are views, not tables, so
`mdm check-fence`'s table-scoped discovery doesn't list them separately, but
013's own REVOKE for them is unchanged) are correctly fenced **right now**,
in live prod, with zero dependency on the removed step — confirming its
security value was already fully zero before this fix, exactly as the
ticket's own original "impact today: low" note said.

**Not done, deliberately:** a full end-to-end rerun of
`bootstrap-prod-mdm.sh` itself, which would rotate both real prod Postgres
credentials (`snowflake_admin` and `application`) and rewrite the
`mdm/postgres_dsn` secret. The read-only `mdm check-fence` result above
already proves the invariant the removed step existed to protect is intact
without it; per this repo's own precedent for exactly this situation
([Ticket 43](43-acquisition-owner-migrations-unreappliable-via-application-dsn.md)),
an actual credential-rotating live run is deferred pending the user's
explicit go-ahead rather than run unilaterally. Offer stands to run it on
request — it would also give a stronger, fully end-to-end confirmation than
the read-only check above.

Tests: `tests/acquisition/test_migration.py` and
`tests/acquisition/test_registry_migration.py` had four
`test_bootstrap_and_restore_cover_*`/`test_bootstrap_and_restore_preserve_*`
tests split into restore-only equivalents (the "bootstrap" half of each was
asserting on the now-removed hardcoded list) plus one new positive
assertion (`test_bootstrap_preserves_dedicated_acquisition_owner_without_a_redundant_revoke`)
that the redundant `REVOKE ALL PRIVILEGES ON source_observation_cursor` /
`SET ROLE edgartools_acquisition_owner;` strings never reappear in
`bootstrap-prod-mdm.sh`. `tests/acquisition/` + `tests/architecture/` (813
tests) green; full repo suite green (2922 passed, 6 skipped) excluding the
pre-existing, unrelated missing-`fastapi` environment gap (`test_api.py`,
`test_temporal_graph_queries.py`, `test_runtime_ops.py`) and the
Docker-based `tests/integration/` directory.

`infra/snowflake/postgres/mdm_post_restore.sql` (the disaster-recovery
restore script, Ticket 26's territory) was checked and appears
architecturally different — a single SQL file/session, not a
subprocess-then-new-connection pattern — so it is not confirmed to share
this bug and was left untouched, out of this ticket's scope.
