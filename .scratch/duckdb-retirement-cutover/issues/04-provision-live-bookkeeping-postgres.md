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

**Status:** tooling built; live execution still blocked on the Ticket
03/13/14/15 caller-repointing chain

- [x] Provisioning tooling built: dedicated `bookkeeping_app` Postgres role
      (independent of MDM's `application` credential), `bootstrap-
      bookkeeping-postgres.sh`, the `bookkeeping/postgres_dsn` Terraform
      secret container + manifest entry, conditional `BOOKKEEPING_DATABASE_URL`
      injection in `deploy-aws-application.sh`, and an `install.sh` stage —
      all local-only, nothing executed against live prod
- [ ] Read-only connectivity check against the live target account passes
      before any DDL runs
- [ ] Provisioning script executed against live prod Snowflake; all 11
      tables exist, additive grants applied
- [ ] `has_table_privilege` sweep run after the script's actual last step
      (not just after DDL) confirms no unintended `snowflake_write` access
      was re-granted
- [x] `mdm check-fence` coverage of the new tables: confirmed **not**
      covered and not expected to be (per-database catalog visibility,
      no fenced tables of its own) — re-verify live once the database
      exists, but the gap itself is understood, not undocumented
- [ ] A real end-to-end smoke test (e.g. a lease acquire/release cycle, a
      checkpoint read/write) against the live new store succeeds
- [ ] Empty-start behavior confirmed live, and the deploy runbook note from
      Ticket 02 is cross-checked against what actually happened
