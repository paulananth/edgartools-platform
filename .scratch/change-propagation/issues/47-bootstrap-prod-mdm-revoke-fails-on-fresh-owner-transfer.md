# 47 — `bootstrap-prod-mdm.sh`'s follow-up REVOKE fails deterministically on a freshly owner-transferred table

**What to build:** Diagnose and fix the root cause of a reproducible
(2/2) failure in `bootstrap-prod-mdm.sh`'s own post-`mdm migrate` REVOKE
step, so a future first-time run of an owner-gated migration doesn't
require manual recovery.

**Blocked by:** None — can start immediately.

**Status:** open

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

- [ ] Root cause identified with live evidence (not just eliminated
  candidates).
- [ ] Fix applied so `bootstrap-prod-mdm.sh` completes end-to-end
  (including the application credential rotation and final REVOKE
  reapplication) on a from-scratch or re-bootstrap run without manual
  intervention.
- [ ] Verified live against prod (or an equivalent from-scratch
  provisioning run) at least once, not just reasoned about.
