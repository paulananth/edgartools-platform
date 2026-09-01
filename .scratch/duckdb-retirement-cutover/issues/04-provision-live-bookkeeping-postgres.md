# 04 — Provision the Bookkeeping Postgres Instance in Live Prod

**Split from the original Ticket 02 during implementation (2026-08-28)** —
see [Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md)'s own
split note. This is the live, hard-to-reverse infra step, deliberately last:
run the provisioning tooling against real prod Snowflake, only after the
full caller-repointing chain's code is tested and reviewed — not before.
This matches the order every "applied live to prod" entry in CLAUDE.md's
history follows: script written and tested first, live execution as its
own confirmed, later action.

**Note (2026-08-29):** the caller-repointing ticket this depends on split
further, same day, into [Ticket 03](
03-rewrite-cross-store-joins-and-repoint-callers.md) (new store methods +
instantiation convention), [Ticket 13](13-rewrite-cross-store-join-sites.md)
(the join sites), [Ticket 14](
14-repoint-warehouse-orchestrator-bookkeeping-callers.md)
(`warehouse_orchestrator.py`), and [Ticket 15](
15-repoint-remaining-bookkeeping-callers.md) (everything else) — this
ticket's live-execution half is blocked on the whole chain, not just
Ticket 03 alone. Left the rest of this file's prose referring to "Ticket
03" as shorthand for that full chain rather than rewriting every mention.

**Split again, same day, before the live-run half started:** while
resuming this ticket, the tooling it assumed already existed (a single
"Ticket 02's provisioning script") turned out to only cover schema DDL
(`infra/scripts/provision_bookkeeping_schema.py` — creates the 11 tables
against an already-open connection, nothing about the Postgres instance,
database, role, or secret around it). Getting from "11 tables can be
created" to "a live DSN a container can actually read" needed real new
work, resolved this session:

- A dedicated Postgres LOGIN role for this store, confirmed independent of
  MDM's `application` credential — Snowflake's own docs (fetched live)
  confirm `snowflake_admin` can `CREATE ROLE ... WITH LOGIN PASSWORD` a
  fully self-managed role, bypassing the `RESET ACCESS` mechanism
  entirely for it. Chosen over the alternative (share `application`, needing
  a dual-secret-write whenever either is rotated) specifically to avoid the
  coupling risk an advisor consultation flagged before any code was written.
- `infra/scripts/bootstrap-bookkeeping-postgres.sh` (new): creates the
  `bookkeeping` database and `bookkeeping_app` role/grants on the *existing*
  MDM Postgres instance (one `snowflake_admin` rotation, not two — see the
  script's own header for why this shape needs one fewer rotation than
  `bootstrap-prod-mdm.sh`), provisions the 11 tables as `bookkeeping_app`
  itself, writes `<prefix>/bookkeeping/postgres_dsn`, re-closes the
  acquisition-ledger fence, and verifies connectivity.
- Terraform: `aws_secretsmanager_secret.bookkeeping_postgres_dsn` (empty
  container, `infra/terraform/modules/warehouse_runtime/main.tf`) plus its
  output, threaded through both account roots.
- `secrets-manifest.json`: declared the new secret name (required before
  any script can resolve it).
- `deploy-aws-application.sh`: `BOOKKEEPING_DATABASE_URL` now injects into
  the warehouse task definition's `secrets` block alongside
  `MDM_DATABASE_URL`, resolved by name the same way — but **conditionally**,
  not hard-required, since no caller depends on it yet (Ticket 03 still
  hasn't repointed anything).
- `infra/scripts/install.sh`: a new "Snowflake Postgres: bookkeeping
  provisioning" stage, placed directly after the existing MDM Postgres
  prerequisites stage (reuses that stage's own `mdm_instance_name`, no new
  instance/network policy).

**None of this executed against live prod** — every check this session ran
was local (bash syntax, Python heredoc compilation, `terraform validate`,
a SQLite-backed exercise of the exact import/provisioning code path). The
install.sh stage is inert until an operator runs `deploy --apply`. This
ticket's live-execution scope below is **unchanged and still blocked** —
building the tooling doesn't shortcut the "only after Ticket 03" ordering
this ticket's own opening paragraph establishes, since nothing has actually
touched the live account yet.

**(Superseded — see the 2026-09-01 note further below.)** The live account
*has* since been touched, by a different session, without this file being
updated at the time.

**What to build (live-execution half — still blocked on Ticket 03):**

- Run a read-only connectivity check against the target Snowflake account
  first, before any DDL statement — confirm you're talking to the current
  live account (`PRJEDJU-QJB05385` as of this writing, per `snow connection
  list`'s `edgartools-prod` entry; re-verify this hasn't changed rather
  than trusting this ticket's own stale value).
- Run the "Snowflake Postgres: bookkeeping provisioning" `install.sh` stage
  (or `infra/scripts/bootstrap-bookkeeping-postgres.sh` directly) against
  live prod.
- **Verify grants with a live `has_table_privilege` sweep run *after* the
  script's actual last step** — not just after the DDL statements. CLAUDE.md
  documents that this platform re-grants `snowflake_write`'s baseline DML
  access as a side effect of rotating *either* `application`'s or
  `snowflake_admin`'s credentials, and a prior `bootstrap-prod-mdm.sh` run
  silently reopened an identical fence this same way. The new script's own
  last mutating step already re-runs `mdm migrate` for exactly this reason
  (it rotates `snowflake_admin` once, which alone is enough to reopen the
  fence) — this checklist item is about confirming that held live, not
  discovering whether it's needed.
- `mdm check-fence` (`edgar_warehouse/mdm/fence_monitor.py`) does **not**
  cover these tables and isn't expected to: it discovers live from
  `pg_class`/`pg_roles` through MDM's own DSN, which is scoped to the `mdm`
  database — Postgres catalog visibility is per-database, so a sibling
  `bookkeeping` database is invisible to it regardless of role. This is
  fine on the merits (bookkeeping has no acquisition-ledger-style fenced
  tables of its own to miss), reasoned through with an advisor before any
  code was written rather than assumed; no separate fence-monitor coverage
  is planned for this store. Re-verify this reasoning still holds once the
  live database actually exists, but treat it as the answer, not an open
  question to re-litigate from scratch.
- Confirm the new store starts empty as expected (no accidental data
  carried over), and that [Ticket 02](
  02-move-bookkeeping-tables-to-snowflake-postgres.md)'s empty-start
  behavior (every CIK reverts to pending) is now genuinely in effect —
  this is the point where that operator-accepted cost actually lands, not
  a hypothetical anymore.

**Blocked by (live-execution half only):**
[Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md),
[Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md),
[Ticket 13](13-rewrite-cross-store-join-sites.md),
[Ticket 14](14-repoint-warehouse-orchestrator-bookkeeping-callers.md),
[Ticket 15](15-repoint-remaining-bookkeeping-callers.md)

**Status:** live-execution half is DONE — discovered already-provisioned,
not run by this session (see note below), then verified live end-to-end.

**Note (2026-09-01): the live provisioning had already happened, untracked
by this ticket file.** Resuming this ticket (via `/implement ticket 04` on a
fresh branch/worktree off current `main`) found `edgartools-prod/bookkeeping/
postgres_dsn` already populated with a real, valid `postgresql://` DSN —
`CreatedDate: 2026-08-31T19:37:45-04:00`, `LastChangedDate: 19:39:20`, i.e.
written ~2 minutes after Terraform created the (intentionally versionless)
secret container. This lines up with the already-merged `codex/daily-
incremental-memory-cleanup` branch (`e4caa4be`/`944de54a`, "allow ECS to
read bookkeeping DSN") and an in-flight `daily-incremental` execution
(`daily-memory-cleanup-f9952462-r3-...`, started 19:51:56 that same
evening) that was already reading it from the live ECS task definition
(`edgartools-prod-large:233`) — so another session (Codex, per branch
naming) ran the live provisioning as part of that work without updating
this ticket file. Nothing was broken by the gap — it's a tracking miss, not
an incident — but flagging it as the same "sibling path executed, ticket
never told" shape CLAUDE.md documents elsewhere for code changes, this time
for a live infra step.

This session verified the already-provisioned state directly rather than
re-running the mutating script (which would have pointlessly rotated
`bookkeeping_app`'s password and `snowflake_admin` a second time against a
store already in the correct state):

- [x] Read-only connectivity check against the live target account passes
      before any DDL runs — `SHOW POSTGRES INSTANCES` confirms
      `EDGARTOOLS_PROD_MDM`, `state: READY`, on `edgartools-prod`
      (account `PRJEDJU-QJB05385`, matching this ticket's own stale
      value); `bootstrap-bookkeeping-postgres.sh --dry-run` against it
      also passes clean.
- [x] Provisioning script executed against live prod Snowflake; all 11
      tables exist, additive grants applied — confirmed live via a direct
      SQLAlchemy connectivity + inspection pass through the real
      `bookkeeping_app` DSN (fetched via `aws secretsmanager get-secret-
      value`, piped directly into a Python process, never echoed to the
      terminal): all 11 `BOOKKEEPING_TABLES` present, all readable.
- [x] `has_table_privilege` sweep run after the script's actual last step
      confirms no unintended `snowflake_write` access was re-granted —
      **corrected mechanism, per advisor consult**: the ticket's own
      "provision the new database" framing doesn't have a
      `snowflake_write`-leak surface of its own (nothing is fenced on
      `bookkeeping`), but the script's one `snowflake_admin` `RESET
      ACCESS` rotation reopens the **MDM** acquisition-ledger/registry
      fence (CLAUDE.md's "snowflake_write RESET ACCESS re-grant" note) —
      the script's own last step already re-runs `mdm migrate` to re-close
      it. Verified live via `mdm check-fence` through the ordinary
      `application` DSN: `is_clean: true`, `leak_count: 0`,
      `access_gap_count: 0`, `exit_code: 0`.
- [x] `mdm check-fence` coverage of the new tables: confirmed **not**
      covered and not expected to be (per-database catalog visibility,
      no fenced tables of its own) — re-verified live now that the
      database genuinely exists; reasoning holds.
- [x] A real end-to-end smoke test (lease acquire/release, checkpoint
      read/write) against the live new store succeeds — ran directly
      against `BookkeepingStore` through the real DSN:
      `acquire_pipeline_run_lease`/`get_pipeline_run_lease`/
      `release_pipeline_run_lease` round-tripped correctly (`held` →
      `idle`), `upsert_source_checkpoint`/`get_source_checkpoint`
      round-tripped correctly. Used an isolated `_ticket04_smoke_test`
      lease/checkpoint key throughout — never touched the real
      `sec_fetch_active` lease, which the in-flight `daily-incremental`
      execution was actively holding at the time. All smoke-test rows
      deleted afterward.
- [x] Empty-start behavior confirmed live, and the deploy runbook note
      from Ticket 02 is cross-checked against what actually happened —
      `get_table_counts()` shows all 11 tables at 0 rows, both before and
      after this session's smoke test (smoke-test rows were cleaned up).
      Matches `docs/runbook.md`'s "Bookkeeping Store Cutover" note
      exactly: the store started empty, not migrated from DuckDB state.

**Separately observed, out of this ticket's scope, not touched:** the
`daily-incremental` execution live at the time of this verification
(`daily-memory-cleanup-f9952462-r3-20260831T235152Z`) is retrying
`RunWarehouseTask` on repeated `OutOfMemoryError`/exit 137 against
`edgartools-prod-large:233` (8192MB) — unrelated to bookkeeping
provisioning (the failure is a container OOM kill, not a DSN/connection
error), and already the subject of separate, already-merged memory-fix work
(`f9952462`, "release memory between source export loads"). Not
investigated further here.
