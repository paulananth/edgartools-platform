# RDM tables that hold published versions only

Status: resolved
Type: task
Owner: Claude

## Question

RDM's tables hold draft code-set versions beside published ones (8 of its 9 tables; only `rdm.code_path` is written
at publish alone), so no whole RDM table is a final output (data-platform FINAL-TABLES.md). The published-only form
exists as the view `rdm.code_context`, which the managed mirror cannot carry. Operator, 2026-11-17: "Published-only
RDM tables (Recommended)".

## Checklist

- [x] Ticket 01 (the approved exposure manifest) is merged: `rules/exposure.yaml` exists, verified in the worktree 2026-11-18 20:40 ET
- [x] Consult the GoF reviewer: verdict "leave it, filter in the mirror". Not taken: drafts sit in the same `code` rows as published ones, so a mirrored base table carries them, and the operator chose published-only tables. Kept from it: one writer (the table is filled from `rdm.code_context`, and a test compares the two) 2026-11-18 20:40 ET
- [x] Design: one table, `rdm.published_code`, the view's columns minus the mutable ones (`valid_to`, status); retired and superseded are derivable from the later `valid_from`. One writer, `rdm.write_published_codes` (SECURITY DEFINER, so the runtime has no write right on the table), and an insert/update/delete guard 2026-11-18 20:40 ET
- [x] Build: migration `001-published-code.sql` (with its back-fill, run before the guard exists), the grant in `database.py`, the call in `store.publish` (PostgreSQL; the MySQL engine's frozen migrations are out of scope: the hosted store is PostgreSQL) 2026-11-18 20:40 ET
- [x] Prove on a disposable PG16: only published versions appear, a retired one keeps its rows, equals `rdm.code_context` both ways, update/delete/direct insert refused, an approved version writes nothing, the migration fills a populated store (`tests/integration/test_rdm_published_postgres.py`, 11 tests; with the RDM, context and reference-storage tests, 90 passed in 72 s) 2026-11-18 20:40 ET
- [x] Add it to `rules/exposure.yaml` (new `rdm` layer; version `exposure-2026-11-18.silver-mdm-and-published-rdm-codes`); exposure unit and integration tests pass 2026-11-18 20:40 ET
- [x] Update the runbook and skills: init.md steps 3, 4 and the mirror section (one mirror per store: MDM, Silver, RDM), HOSTED-MIRRORING.md gate, FINAL-TABLES.md 2026-11-18 20:40 ET
- [x] Apply the migration on the hosted store (`edgar-warehouse rdm migrate` with the owner login; both migration files now recorded): `published_code` holds 7,378 rows of 15 versions, the same codes as `rdm.code_context` in both directions, every column commented, and the loader login's update and insert are refused 2026-11-18 21:28 ET
- [x] Learning → skill: `FINAL-TABLES.md` and `HOSTED-MIRRORING.md` say RDM's final output is `rdm.published_code` and a mirror is per store (PR 1901); `CONNECTIONS.md` says a driver's connection error can print the address and password, so a direct check prints only the exception type and any command that may fail on a connection is filtered (this ticket's apply-step check printed the loader login's address) 2026-11-18 21:41 ET

Blocked by: 01
