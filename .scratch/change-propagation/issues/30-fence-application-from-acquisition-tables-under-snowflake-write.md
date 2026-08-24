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

**Status:** ready-for-agent

- [ ] Confirm whether `snowflake_write`'s blanket grant on new tables is a
  Snowflake Postgres platform guarantee (i.e. will recur for every future
  acquisition-ledger table a later migration creates, so REVOKE would need
  to run for each) or a one-time artifact of how migration 013 happened to
  run — check Snowflake's own Postgres documentation and/or ask Snowflake
  support if the account-level docs don't say.
- [ ] Decide and implement the fencing fix (or the deliberate non-fix,
  documented as such) for the nine objects listed above.
- [ ] Correct `models.py`'s `SourceExpectedProducerRecord` docstring to match
  whatever the real, verified enforcement boundary is after this ticket,
  not the aspirational claim it makes today.
- [ ] Verify live against prod: `application` (no `SET ROLE`) can no longer
  read/write the nine objects directly, while `SET ROLE
  edgartools_acquisition_processor` (etc.) still can.
