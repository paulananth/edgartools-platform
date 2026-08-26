# 30 — Fence `application` from acquisition ledger tables under Snowflake Postgres's `snowflake_write` role

**What to build:** Migration 013's authority model (Ticket 03/14/18/19) assumes
that revoking `application`'s direct grants on the nine acquisition ledger
objects (`source_observation_cursor`, `source_fetch_decision`,
`source_fetch_work`, `source_fetch_transition`, `source_revision`,
`source_processing_decision`, `source_expected_producer`,
`source_change_status`, `source_change_status_detail`) is sufficient to force
runtime code through `SET ROLE`-gated sub-roles (`edgartools_acquisition_*`).
Live verification during Ticket 29's prod deploy proved that assumption false
in this specific Snowflake Postgres environment: `application` is also an
inherited (default `rolinherit=true`), non-optional member of
`snowflake_write` — a Snowflake-Postgres-managed platform role
(`snowflake_admin_group`, `snowflake_write`, `snowflake_read_only`,
`snowflake_replication`, `snowflake_insights`, etc., confirmed via `SHOW`
against `pg_roles`) — and `snowflake_write` itself holds full DML (`SELECT`,
`INSERT`, `UPDATE`, `DELETE`, `REFERENCES`, `TRIGGER`, `TRUNCATE`) on every
table, including these nine, regardless of migration 013's explicit
per-object `REVOKE ... FROM application`. Confirmed live:
`application` (no `SET ROLE`) reads `source_fetch_decision` directly and
`has_table_privilege('application', 'source_fetch_decision', 'SELECT')`
returns `true`. `models.py`'s `SourceExpectedProducerRecord` docstring
currently claims column-scoped GRANTs are "the sole enforcement layer here" —
that claim is false in prod today.

`pg_default_acl` was checked and does not explain `snowflake_write`'s grant
on `source_fetch_decision` (no default-ACL rule targets it); the grant most
likely comes from Snowflake's own managed-service automation outside
`pg_default_acl`'s visibility, not a plain Postgres `ALTER DEFAULT
PRIVILEGES` rule anyone in this repo issued.

This ticket resolves: is fencing `application` away from `snowflake_write`'s
ambient access on these nine objects worth doing, and if so, how — options
include (a) `REVOKE ALL ... FROM snowflake_write` on just these nine objects
(inside migration 013's own post-ownership-transfer `DO` block, `SET ROLE
edgartools_acquisition_owner` first, mirroring Ticket 29's
`bootstrap-prod-mdm.sh` fix for the identical ownership-timing issue), (b)
accepting the ambient access as an unavoidable platform characteristic and
weakening the docstring's enforcement claim instead, or (c) something else.
Whichever is chosen must not touch `application`'s `snowflake_write`
membership itself (blast radius: all 19 `mdm_*` tables plus whatever
Snowflake's own platform tooling depends on that membership for) and must be
checked against Snowflake Postgres's actual behavior — not just Postgres
documentation — since `snowflake_write` is not a construct vanilla Postgres
defines.

**Blocked by:** None — can start immediately. Surfaced while resolving
[29 — Deploy the gated acquisition path to prod and dry-run it](29-deploy-and-dry-run-gated-acquisition-path.md).

**Status:** resolved (2026-08-26) — all four bullets done, verified live
against prod: zero leaked privileges across all 11 fenced objects × both
roles. See the "Bullet 4 resolved" section below for the second platform
behavior this surfaced (RESET ACCESS reopens the fence) and the open
monitoring gap that follows from it.

- [x] Confirm whether `snowflake_write`'s blanket grant on new tables is a
  Snowflake Postgres platform guarantee (i.e. will recur for every future
  acquisition-ledger table a later migration creates, so REVOKE would need
  to run for each) or a one-time artifact of how migration 013 happened to
  run — check Snowflake's own Postgres documentation and/or ask Snowflake
  support if the account-level docs don't say.
- [x] Decide and implement the fencing fix (or the deliberate non-fix,
  documented as such) for the nine objects listed above.
- [x] Correct `models.py`'s `SourceExpectedProducerRecord` docstring to match
  whatever the real, verified enforcement boundary is after this ticket,
  not the aspirational claim it makes today.
- [x] Verify live against prod: `application` (no `SET ROLE`) can no longer
  read/write the nine objects directly, while `SET ROLE
  edgartools_acquisition_processor` (etc.) still can.

## Progress (2026-08-26)

**Bullet 1 — confirmed a recurring platform guarantee, correcting this
ticket's own earlier claim.** A second, more targeted live query (read-only,
via the `application` DSN) found `pg_default_acl` rows this ticket's
original check missed: two `defaclrole='application'` rows granting
`snowflake_write` full DML (`arwdDxt`) — one scoped to schema `public`, one
database-wide (`defaclnamespace='-'`). Neither `bootstrap-prod-mdm.sh` nor
`infra/snowflake/postgres/mdm_post_restore.sql` (the repo's own MDM
provisioning scripts, both read in full) create any default-ACL rule naming
`snowflake_write` as grantee anywhere — this is Snowflake Postgres's own
managed-service automation, not something this repo issued. Since it's a
standing default-ACL rule (not a one-time grant already baked into the nine
existing tables), it will recur for every future table `application` (or,
plausibly, any role — not independently re-verified per-role) creates,
including future acquisition-ledger tables. **Practical consequence: a
per-table REVOKE (option (a)) is not "fix once" — it must be re-applied to
every new acquisition-ledger table a future migration creates**, unless the
default-ACL rule itself is also revoked (which the ticket's own blast-radius
constraint rules out touching, since it isn't scoped to just these nine
objects).

**Bullet 3 — done.** Corrected both false claims: `models.py`'s
`SourceExpectedProducerRecord` docstring and
`013_acquisition_ledger.sql`'s Ticket 19 grant comment now state the real
boundary (column-scoped GRANTs hold among the acquisition sub-roles, but not
against `application`'s ambient `snowflake_write` membership) instead of
claiming GRANTs are the sole enforcement layer.

**Bullets 2 and 4 — blocked, not yet decided.** Before implementing option
(a) (`REVOKE ALL ... FROM snowflake_write` inside migration 013's own
post-ownership-transfer `DO` block), ran one live write-experiment on a
disposable probe table to test whether such a REVOKE can even be issued as
`edgartools_acquisition_owner` from the `application` DSN. `ALTER TABLE
_ticket30_probe OWNER TO edgartools_acquisition_owner` appeared to succeed,
but the immediately following `SET ROLE edgartools_acquisition_owner`
failed with `InsufficientPrivilege: must be able to SET ROLE
"edgartools_acquisition_owner"` — and a direct `pg_has_role('application',
'edgartools_acquisition_owner', 'MEMBER')` enumeration confirms `application`
has **no** membership in that role, not even a non-inheriting one. How the
prior `ALTER TABLE ... OWNER TO` and a later `DROP TABLE` on that same probe
table both apparently succeeded despite that is unexplained — stopped
further live experimentation on prod rather than continue probing an
incompletely-understood permission model (probe table confirmed cleaned up,
no orphan left behind).

Filed [43 — Migration 013's owner-gated statements have no live deploy path
via the `application`
DSN](43-acquisition-owner-migrations-unreappliable-via-application-dsn.md):
independently confirmed `application` is the *only* credential the real
deploy path (`edgartools-prod-mdm-utility`'s `mdm_migrate` mode) ever
connects with, and `_apply_acquisition_ledger_migration`'s
`may_manage`-gated rerun silently no-ops for any connection lacking
`edgartools_acquisition_owner` membership. This means option (a), as
originally scoped, has no confirmed way to actually reach prod through the
platform's standard deploy path — resolving Ticket 43 (or getting a more
privileged Postgres credential from the user) is a prerequisite for
finishing bullets 2 and 4 of this ticket, not just a nice-to-have.

**Update (2026-08-26): option (iii) chosen** — landed option (a)'s fix as
code/SQL with automated test coverage, deferring live prod application to a
follow-up once Ticket 43 (or a more privileged credential) is available.

**Bullet 2 — done.** `013_acquisition_ledger.sql` gained a second, guarded
`DO $$ ... $$;` block immediately after the existing `application` REVOKE,
scoped to the same nine objects: `REVOKE ALL PRIVILEGES ON <9 objects> FROM
snowflake_write;`, wrapped in `IF EXISTS (SELECT 1 FROM pg_roles WHERE
rolname = 'snowflake_write')` so it's a genuine no-op against a plain
Postgres instance (local/test) rather than an error, and runs under
`edgartools_acquisition_owner` automatically (same execution path as the
`application` REVOKE immediately before it — `_apply_acquisition_ledger_
migration` runs every statement after the first under `SET LOCAL ROLE
edgartools_acquisition_owner`, and that role already owns all nine objects
via the `ALTER ... OWNER TO` statements earlier in the file, so REVOKE
doesn't need to match the original grantor). Deliberately does not touch
`application`'s `snowflake_write` role membership itself, matching the
ticket's blast-radius constraint. `models.py` and `013`'s Ticket 19 comment
were already corrected under bullet 3.

**New test proves the fix actually revokes access, not just that the SQL
parses:** `tests/integration/test_acquisition_ledger_postgres.py::
test_snowflake_write_ambient_access_is_revoked_on_the_nine_ledger_objects`
creates a role literally named `snowflake_write` in the real (Dockerized)
Postgres fixture, grants it privileges on two representative objects the
way the platform's own automation would, re-applies the (idempotent)
migration, and confirms `has_table_privilege` flips `true → false` for both
— a real Postgres role-graph proof, not a SQLite stand-in (this exact class
of gap — SQLite can't model real GRANT/role semantics — is why the Source
Family Registry Postgres-only bugs existed; same lesson applied here
up front). Full file: 9/9 passed. `tests/acquisition` + `tests/mdm`: 772/772
passed. No regression in the existing `application`-REVOKE proof in the same
file (`test_postgres_roles_proofs_and_fencing_are_enforced` still passes
unchanged).

**Bullet 4 — still blocked, unchanged from before.** This fix cannot be
applied to real prod through the standard `mdm migrate` deploy path today —
that path connects as `application`, which has no membership in
`edgartools_acquisition_owner`, so `_apply_acquisition_ledger_migration`
silently no-ops before reaching this statement (Ticket 43). Live prod
verification (`application` denied, `SET ROLE
edgartools_acquisition_processor` etc. still permitted) needs either Ticket
43 resolved or a more privileged Postgres connection supplied by the user.

## Bullet 4 resolved (2026-08-26) — and a second, more severe platform behavior found live

Ticket 43 unblocked the deploy path (`bootstrap-prod-mdm.sh`'s `snowflake_admin`
credential). Ran it live against prod. `mdm migrate` completed successfully
and the REVOKE statement executed with no error — but a full `has_table_privilege`
sweep immediately after showed **all 11 objects (the original 9 plus the two
014/Ticket-20 registry tables) still fully leaking for both `application` and
`snowflake_write`**, contradicting a successful, error-free migration run.

**Root cause, confirmed by direct, isolated reproduction (apply REVOKE,
verify revoked, call `RESET ACCESS` again with zero other writes in between,
re-verify):** `ALTER POSTGRES INSTANCE ... RESET ACCESS FOR '<role>'` itself
re-grants `snowflake_write`'s baseline DML access to these objects as a
platform side effect — confirmed for **both** `RESET ACCESS FOR
'snowflake_admin'` and `RESET ACCESS FOR 'application'`. This is a
previously-undocumented Snowflake Postgres platform behavior, distinct from
and more severe than the standing `pg_default_acl` rule bullet 1 already
found (that rule explains why *new* tables get the grant; this explains why
an *already-revoked* table's grant comes back). Practical consequence:
`bootstrap-prod-mdm.sh`'s own normal run order — `mdm migrate` (applies the
REVOKE) *then* `RESET ACCESS FOR 'application'` (silently reopens it) — means
**every normal run of the script left the fence open**, not just my
diagnostic rotations.

**Second, independent gap found in the same pass:** migration 014
(`014_source_registry.sql`, Ticket 20) only ever revoked `application`'s own
direct grant on `source_registry_version`/`source_registry_coverage` — it
never got the equivalent `snowflake_write` REVOKE this ticket added to 013.
Same shape as 013's original gap, on the sibling migration; fixed the same
way (mirrored block, guarded on `snowflake_write` existing).

**Fixes shipped:**
- `014_source_registry.sql` gained the same `snowflake_write` REVOKE block
  013 has, scoped to its two objects.
- `bootstrap-prod-mdm.sh` gained a new step, immediately after the
  `application` RESET ACCESS + secret write and before the optional
  Snowflake-secret population: a fresh `snowflake_admin` rotation followed
  by re-running `mdm migrate` (idempotent) as the script's true last
  database-mutating operation — so both RESET ACCESS calls' side effects are
  corrected before the script exits, not just the first.

**Live state after both fixes, verified via `has_table_privilege` across all
11 objects × both roles × SELECT/INSERT/UPDATE/DELETE: zero leaks.** This is
the first time bullet 4's acceptance criterion has actually been met.

**Open, unresolved risk — this is a live gap, not just a historical note:**
any future credential rotation of `snowflake_admin` or `application` on this
instance (including one run *outside* `bootstrap-prod-mdm.sh`, e.g. a manual
`RESET ACCESS` for incident response) reopens this fence until the next `mdm
migrate` run, and **nothing currently monitors for that drift**. The fix
inside `bootstrap-prod-mdm.sh` only protects runs that go through that exact
script end-to-end. A periodic live check (the same `has_table_privilege`
sweep used to verify this ticket) running on a schedule, alerting if either
role regains access, is the natural follow-up — not filed as its own ticket
yet; flagging here for whoever picks this map back up.

**Process note:** while diagnosing this, a `snow sql ... RESET ACCESS FOR
'application'` command's raw JSON output (containing the new plaintext
`application` password) was piped through `tail` directly into visible tool
output instead of straight into a credential-consuming script, briefly
exposing it in this session's transcript. Caught immediately; the exposed
password was invalidated by rotating `application` again through the correct
piped pattern (`snow sql ... | python3 <extractor> | bootstrap-aws-mdm-secrets.sh
--password-stdin`, never touching stdout) before any further action, and the
AWS secret was rewritten to match. No other script or process ever saw the
exposed value. Every other credential handled in this session's diagnostics
went through the same safe piped pattern from the start; this was the one
exception, caused by an ad hoc one-off command written outside that pattern
for a quick manual check.
