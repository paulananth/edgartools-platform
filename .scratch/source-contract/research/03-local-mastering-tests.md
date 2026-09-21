# Research 03: can mastering test cases run on a laptop?

Ticket: [03-can-mastering-test-cases-run-locally](../issues/03-can-mastering-test-cases-run-locally.md)
Map: [Source Contract](../map.md), acceptance checks 4 (no network) and 8 (one command).
Date: 2026-09-21. Branch `claude/source-contract-map`. All citations are `path:line` in this worktree.
Clean MDM files were read only. Nothing under `edgar_warehouse/mdm/clean/`, `docs/specs/clean-mdm/` or `.scratch/clean-mdm/` was changed.

## Answer in brief

- **Yes, but only against a real PostgreSQL 16.** There is no SQLite or in-memory path. A disposable
  `postgres:16-alpine` container on Colima, bound to `127.0.0.1`, is enough. It needs no network once the
  image is pulled and the uv cache is warm.
- **Main limit on what a test can claim:** the Merge Stage does not choose bindings today. Automatic rules
  are rejected, so "the engine bound this record to identity X" cannot be tested. A test *can* check that a
  steward-declared bind is accepted or vetoed. It can also check create (with a declared identity and bind),
  `binding_required` (unbound), deferred with a reason, and field survivorship.
- **Measured cost:** the container is ready in about 16 s. Setup for each test (full migration and
  registration) takes about 3-7 s. A simple Merge Stage call takes about 1.4-1.8 s. The current fixture waits
  only about 8 s for readiness, so it failed on 4 of 7 runs on this machine.

---

## 1. What the Merge Stage needs to run

### Store: PostgreSQL 16 only

| Requirement | Evidence |
| --- | --- |
| Store refuses any non-Postgres engine | `edgar_warehouse/mdm/clean/store.py:243-244` (`Store.__init__`), `store.py:47-48` (`migrate`) |
| Server must be **major version 16 exactly** | `store.py:54-55` (`server_version_num // 10000 != 16` raises) |
| The commit capability is PL/pgSQL `SECURITY DEFINER` | `edgar_warehouse/mdm/migrations/023_clean_mdm.sql:110-111`; later redefined in `027_clean_mdm_deferred.sql:15-16` and `028_clean_mdm_assessment.sql:124-141` |
| Merge SQL uses Postgres-only features: `jsonb` operators, `?|`, `ANY(:array)`, advisory locks | `edgar_warehouse/mdm/clean/merge.py:52-54`, `merge.py:286`, `merge.py:512-516` |
| Preview uses a rollback-only SQL capability | `merge.py:552-590`, `028_clean_mdm_assessment.sql:128` |

SQLite and in-memory stores are not possible without changing Clean MDM. The existing SQLite
fixture in `tests/mdm/conftest.py:88-102` serves the legacy MDM model, not `mdm_v2`.

### Roles

- The migration owner and the runtime role must differ (`store.py:57-58`).
- The runtime role must exist with no superuser, createdb or createrole privilege (`store.py:59-67`).
- After migration, the runtime role gets only `USAGE`, `SELECT` and `EXECUTE` on the capability functions
  (`store.py:120-137`). The migration **fails** if the role keeps any direct INSERT, UPDATE, DELETE or
  TRUNCATE (`store.py:145-151`).
- The tests create `clean_application` with `NOSUPERUSER NOCREATEDB NOCREATEROLE`
  (`tests/integration/test_clean_mdm_postgres.py:74-79`).

### Migrations

- `store.migrate` runs `023_clean_mdm.sql`, then `025`-`029`, all checksummed (`store.py:49-106`;
  `docs/specs/clean-mdm/local-operations.md:34-41`).
- `024_clean_mdm_mirror.sql` (the journal mirror) is separate. It is installed by
  `clean.publication.migrate_mirror` into the change-ledger database (`local-operations.md:42-44`), and only
  the CLI or journal path needs it.
- `register_dataset` also needs the acquisition source registry tables `public.source_registry_version` and
  `public.source_registry_coverage` (`store.py:196-201`). The tests install these with migration 014 through
  `_apply_source_registry_migration` (`test_clean_mdm_postgres.py:25,80`;
  `edgar_warehouse/mdm/migrations/runtime.py:453-465`).

### Registered policy digest

- `register_policy` is owner-only. It refuses any non-empty `automatic_rules` and needs distinct, non-empty
  `required_consumers` (`store.py:159-177`).
- `MergeStage._execute` loads the policy by digest. It raises `Unknown or unqualified policy` if the policy
  is missing or has automatic rules (`merge.py:299-304`).
- `commit_batch` also needs non-empty `required_consumers` (`023_clean_mdm.sql:146-147`).

### Registered dataset and registry authority

- `register_dataset` needs exactly one **active** `source_registry_version` row, with a coverage row whose
  `source_family` equals the contract's `family` and is not `remove` (`store.py:196-210`).
- `commit_batch` checks this pinned authority again for every assertion. It also checks that
  `schema_version` matches (`023_clean_mdm.sql:151-160`).
- Dataset contracts are immutable. A changed body needs a new versioned code (`store.py:217-225`).
- **Tension to note:** the spec says "Do not manufacture activation authority to make a run pass"
  (`local-operations.md:46-47`). The tests nevertheless insert an `active` registry version with
  `operator_authorization_reference='offline-fixture'` into their disposable database
  (`test_clean_mdm_postgres.py:97-111`, plus a per-family row at `:1618-1623`). A local mastering runner
  would do the same. It must stay confined to a disposable database, and it should go to Codex as a
  proposal (a named "offline fixture authority").

### Pinned source publication and bounds

- File-backed input is read through `batch_evidence`. It hash-checks the member (`cli.py:87-88`), needs a
  registered dataset (`cli.py:89-95`), and applies `normalize` line by line (`cli.py:101-139`).
- Unsupported rows become deferred records when the adapter sets `retain_deferred` (`cli.py:140-157`).
  `record_count` must be exact (`cli.py:99-100,158-159`).
- A publication gives `publication_key`, `revision` and `effective_at` (`cli.py:108-114`;
  `adapters.py:145-157`).
- Bounds: 1000 assertions plus deferred records per batch (`merge.py:231-236`; `cli.py:104-107`), a
  closure of at most 10,000 (`merge.py:110-112`), and `as_of` with a timezone (`evidence.py:27-31`).
- The CLI path adds `BOOKKEEPING_DATABASE_URL` (`cli.py:317`) and, for `publish --consumer journal`,
  `CHANGE_LEDGER_DATABASE_URL` (`cli.py:339-342`). The spec layout uses three databases
  (`local-operations.md:28-32`). **A direct `MergeStage.apply()` call needs only the MDM database.**

## 2. Existing tests that exercise `mdm/clean`

| File | Tests | Needs Postgres | Fixture / data |
| --- | --- | --- | --- |
| `tests/integration/test_clean_mdm_postgres.py` | 44 | Yes: its own `postgres:16-alpine` container | Synthetic assertions built inline (`source()`, `:360-370`); `tests/fixtures/clean_mdm/v1` (10 records, 8 kinds, 10 identities, 10 bind decisions) |
| `tests/integration/test_clean_source_publications.py` | 31 (incl. parametrized) | Yes: reuses the same `postgres`/`database` fixtures (`:35-38`), plus a database per test (`:55-...`) | `tests/fixtures/clean_mdm/publication_v1` |
| `tests/mdm/test_clean_company_source.py` | 3 | No | Parquet built in `tmp_path` (`:20-60`) |
| `tests/mdm/test_clean_publication_continuity.py` | 12 | No | Pure `plan_continuity` objects |

### Fixture mechanics (Postgres suites)

- **`postgres`** (module scope, `test_clean_mdm_postgres.py:44-89`):
  - Checks that the image is already local with `docker image inspect` and never pulls (`:46`).
  - Runs a uniquely named `--rm` container with the port bound to `127.0.0.1` only (`:47-59`).
  - Polls readiness **80 times × 0.1 s** (`:65-73`).
  - Creates the runtime role (`:74-79`) and installs migration 014 (`:80`).
- **`database`** (**function scope**, `:91-93`) calls `initialize_database` (`:96-148`) for each test. That
  function:
  - drops `mdm_v2`;
  - resets the registry;
  - runs `migrate()` twice, which proves idempotency (`:113-114`);
  - registers a policy and two datasets (`:115-147`).
- **`command_databases`** (`:1032-1068`): used only by CLI and command tests. It creates separate
  Bookkeeping and change-ledger databases, installs the mirror (024), and sets the three `*_DATABASE_URL`
  variables.
- The spec's own acceptance runner uses the same approach, "fails rather than skips missing prerequisites"
  (`local-operations.md:9-12`). It needs no Snowflake and no network source (`local-operations.md:22-24`).

### Measured runtime (this laptop, Colima, `postgres:16-alpine` = PostgreSQL 16.15)

| Run | Result | pytest time | Notes |
| --- | --- | --- | --- |
| The 2 non-Postgres files, cold `.venv` (uv built a new venv from cache) | 15 passed | 109 s | one Parquet test took 75 s cold |
| Same, warm | 15 passed | **3.5 s** (wall 10 s) | |
| Same, `uv run --offline` | 12 passed (continuity file) | 0.23 s (wall 5 s) | proves no network needed once cached |
| `test_reviewed_binding…` + `test_versioned_representative_fixture…` | 2 passed | 39.3 s | container setup **28.5 s**; test setup 2.8 s; calls **1.37 s / 1.83 s** |
| Full `test_clean_mdm_postgres.py` | **43 passed, 1 failed** | **269.6 s** | the failure is `ModuleNotFoundError: fastapi` in the v2 API test (`:1510-1513`); it needs `--extra mdm` (`local-operations.md:10-12`) |
| Full file, 3 other attempts, plus a combined run with `test_clean_source_publications.py` (2 attempts) | all tests **errored** | 26-61 s | `Failed: PostgreSQL did not become ready` (`:73`) |
| Direct probe: `docker run --network none postgres:16-alpine` until `pg_isready` | ready | **16.2 s** | |

Slowest steps in the passing full run:

| Step | Time |
| --- | --- |
| Fresh-replay test (`:1207`) | 28.1 s |
| First container setup | 14.1 s |
| CLI command test (`:1071`) | 12.0 s |
| Native Company test (`:1610`) | 9.9 s |
| Per-test `database` setups | 2.8-7.5 s |

Wall-clock time for the Postgres runs varied from 29 s to 1170 s. The gaps outside pytest's own session
time happened on the first cold venv build and during heavy Colima load. They were not reproduced in a
later timestamped run (83 s wall for a 61 s session).

**Readiness defect:** the fixture waits about 8 s (`test_clean_mdm_postgres.py:65-73`). The container needs
about 16 s here (probe) and took 14-28 s inside the suite. As a result, **4 of 7 container-starting
invocations failed at setup.** This is a steady shortfall in the wait budget on Colima, not a random flake.
`evidence.md:22-24` recorded 116 passing in 52.35 s on a faster setup. Any "one command" runner needs its
own longer readiness budget. It must not reuse this fixture as it stands.

## 3. How a test can declare and seed "existing identities" through supported paths only

**Direct inserts are impossible, not just discouraged.**

- The runtime role has no table write privilege, and `migrate` fails if it gets one
  (`store.py:145-151`).
- The permissions test proves live that `DELETE`, `INSERT` and `CREATE TABLE` by the runtime role fail
  (`test_clean_mdm_postgres.py:231-237`).
- The spec also forbids writing around the Merge Stage: "No adapter, API override, bulk loader, **seed**,
  repair, or reconciliation path writes master state around this entry point"
  (`docs/specs/clean-mdm/merge-stage.md:28-29`).

**The supported seeding path is a first `MergeStage.apply()` batch.** That batch holds the seed source
records, the identity allocations and `bind` decisions. This is what every existing test does:

- `identity_and_binding(a)` returns `{"entity_id", "kind", "published_at"}` plus
  `decision("bind", actor, reason, at, subject=a["subject"], entity_id, evidence=[a["assertion_id"]])`
  (`test_clean_mdm_postgres.py:373-383`; `evidence.py:155-166`).
- `apply(db, n, ...)` calls `MergeStage(Store(app)).apply(...)` with checkpoint `n-1 → n`
  (`test_clean_mdm_postgres.py:386-396`).
- The v1 fixture carries `identities` and `decisions` inline in its manifest batch
  (`tests/fixtures/clean_mdm/v1/manifest.json`; used at `test_clean_mdm_postgres.py:985-998`).

The engine applies these rules to a seed:

| Rule | Evidence |
| --- | --- |
| An existing identity cannot be declared bare. A new identity must be bound in an accepted binding. | `merge.py:366-367` ("New identities require an accepted source binding") |
| A bind must cite an assertion that describes its subject | `merge.py:359-364`; `identity.py:77-78` |
| An identity cannot be allocated twice | `merge.py:353-355` |
| A bind cannot move an established binding | `identity.py:73-76` |

So a "declared existing identity" in a Source Contract must be a **seed record** that goes through the
same adapter. It is not a free-standing row.

Seed values that are hashes can be derived, so a test author never writes a digest by hand:

- `subject = digest([source_code, record_key])` (`evidence.py:34-35`).
- `assertion_id` = digest of the normalized body (`evidence.py:90`), so a runner obtains it by running
  `normalize` on the seed row (`adapters.py:49-158`).
- `decision_id` = digest of the decision body (`evidence.py:165`); `merge.py:241-246` checks it.

A runner can therefore accept "seed: `{source, record_key}` → `entity_id`" and build the batch itself. The
seed's source may be the contract's own dataset or a second registered dataset. Each needs its own
registry-backed `register_dataset` (`store.py:180-233`).

How later batches meet the seed:

- A record whose `(source_code, record_key)` is already bound has the **same subject**. It updates that
  entity through the retained binding (`merge.py:371-373`; `identity.replay`).
- A record from another source that shares a CIK is **not** attached automatically. It stays unbound unless
  the test batch carries an explicit `bind` decision.

## 4. What a test can assert on

Everything is readable from `mdm_v2.projection`:

- `documents(db, kind)` (`test_clean_mdm_postgres.py:399-409`);
- `ContractReader(...).entity(id)` for provenance (`consumer.py:62`; used at
  `test_clean_mdm_postgres.py:1010-1015`);
- `mdm_v2.deferred_record` and the batch `effects->'source_accounting'` (`:1700-1705`).

| Outcome | How it shows | Evidence |
| --- | --- | --- |
| **Bound to identity X** (an existing binding, same subject) | `projection[entity X].subjects` contains the subject; its fields are updated | `merge.py:371-373,424-435` |
| **Bound to X by a declared steward decision** | same as above; or a rejection if kinds or authoritative identifiers conflict (`Conflict`, veto kept by the assessment) | `merge.py:408-413`, `merge.py:167-187`; test `:473-503`, `:1984-2017` |
| **New identity** | only with a declared identity plus a bind: `projection[entity]` with `status: accepted` | `merge.py:424-442`; test `:420-433` |
| **Unbound (would-be create/defer today)** | a review with `reason: binding_required`, `open: true`, `blocking: true`; no entity | `merge.py:446-454,480-493`; test `:412-419` |
| **Deferred with reason** | a review with `object_id = deferred_id`, and a `mdm_v2.deferred_record` row with `reason` from `UnsupportedRecord` | `merge.py:495-510`; `cli.py:140-157`; test `:1689-1705` |
| **Which fields survived** | `fields[name].value`, `.winner` (assertion_id, source_code), `.conflicts` (losers), `.cleared`, `policy_digest` | `merge.py:414-435`; `survivorship.py:270-280`; test `:436-470` |
| **Quarantine** | `status: review`, empty `fields`, reviews `kind_conflict` / `authoritative_identifier_conflict` | `merge.py:389-407,436-441` |
| **Accounting** | `{"normalized", "deferred", "total"}` | `merge.py:546-550`; test `:1705` |

Deferred reasons that exist today:

| Reason | Evidence |
| --- | --- |
| `invalid_cik` | `adapters.py:28` |
| `missing_record_identity` | `adapters.py:45` |
| `invalid_record_shape` | `adapters.py:60` |
| `invalid_identity_kind` | `adapters.py:65` |
| `unsupported_identity_kind` | `adapters.py:68` |
| `invalid_field_shape` | `adapters.py:84` |
| `invalid_json_record` | `cli.py:126` |

**The engine does not choose bindings today.**

- `register_policy` rejects `automatic_rules` (`store.py:161-162`), and `_execute` rejects any policy that
  has them (`merge.py:303-304`).
- The module docstring: "Neither auto binding nor automatic consolidation is enabled in this release"
  (`merge.py:3-4`).
- `normalize` never attaches to an existing master (`adapters.py:54-56`).
- Company Q1-Q13 accept qualified automatic fuzzy binding as a *requirement*, but "the current core still
  rejects automatic rules" (`merge-stage.md:33-40`), and the local build has them disabled
  (`merge-stage.md:211-221`).
- `company_source` prepares input with "no identity bindings included" (`company_source.py:1-4,231`).

What this means for Q3 of the map:

- The expected `bind` / `create` outcome of a mastering test case can only be written as
  **"given these declared steward decisions, the result is …"**, or as **"unbound → `binding_required`"**.
- A case such as "the engine binds this record to X" becomes testable only when a qualified automatic rule
  exists. Its cases should be written now, as expected pending, so they switch on with the rule.
- A new identity is always a declared input, never an inferred output.

`--dry-run` (preview) returns the next batch's projected identities, fields and reviews with every effect
rolled back (`cli.py:249-256`; `merge.py:552-596`; `local-operations.md:87-93`). A preview still needs the
seed to be committed first, because preview runs against the current generation.

## 5. Smallest local setup that meets checks 4 and 8

### Recommended setup

**One disposable PostgreSQL 16 container, one database, two roles, and direct `MergeStage.apply()` calls.
No CLI path, no Bookkeeping and no change-ledger database.**

1. **Prerequisites (one time, done outside the check):**
   - Colima is running.
   - `postgres:16-alpine` has been pulled.
   - `uv sync --frozen --extra s3 --extra mdm-runtime` is done.

   `--extra mdm` (fastapi) is **not** needed. Only the v2 API test imports it
   (`test_clean_mdm_postgres.py:1510-1513`).
2. **The one command:**
   `uv run --offline --frozen --extra s3 --extra mdm-runtime pytest <generic mastering runner> --contract <path>`.
   `--offline` was verified to work with a warm cache (5 s wall).
3. **Network refusal (check 4):**
   - uv runs `--offline`.
   - The image is inspected and never pulled (the `test_clean_mdm_postgres.py:46` approach).
   - The container port is bound to `127.0.0.1` only (`:55`). `--network none` cannot be used, because the
     host must reach the port.
   - The runner should also refuse non-loopback sockets inside the Python process. This belongs to the
     map's check-4 design, not to Clean MDM.
4. **Session setup (module scope):**
   - Start the container, with a readiness budget of **at least 30 s**. The current fixture's 8 s is too
     short (§2).
   - Create the runtime role.
   - Install migration 014 (`_apply_source_registry_migration`).
   - Run `store.migrate`.
   - Add one disposable `offline-fixture` registry version with coverage for the contract's `family`.
   - Call `register_dataset` (the contract's `dataset` block) and `register_policy` (the contract's policy
     or policy reference).
5. **Per test case:**
   - Commit the seed batch (seed rows through the same adapter, identities, bind decisions), then the
     fixture batch, both through `MergeStage.apply()`.
   - Read the projections and deferred records, then compare them with the expected outcomes in §4.
   - **Isolation:** the existing tests re-migrate for each test (2.8-7.5 s). The tables are append-only
     (`test_clean_mdm_postgres.py:238`: `append-only`), so truncating between cases is not an option. A
     cheaper approach is `CREATE DATABASE case_n TEMPLATE migrated` for each case. Roles are cluster-wide,
     so grants carry over. This is **not measured**.

### Runtime

| Part | Time | Basis |
| --- | --- | --- |
| Container ready | ~16 s (up to 28 s under load) | measured (probe; suite setup 14.1-28.5 s) |
| Migration and registration per database | ~3-7 s | measured (`database` setup 2.8-7.5 s) |
| One case (seed commit plus fixture commit and read) | ~1.5-4 s | measured calls of 1.37 s and 1.83 s for 1-2 `apply` calls; estimate |
| **5-case mastering suite, re-migrating per case (current pattern)** | **~45-75 s** | estimate from measured parts |
| 5-case suite with template-database cloning | ~25-40 s | estimate, not measured |
| Parse and mapping cases (`normalize` only, no database) | < 1 s | measured (non-Postgres files: 3.5 s including the 2 s Parquet test) |

### Gaps to hand to Codex as proposals (`.scratch/handover/`), not edits

- The readiness budget in the shared fixture (`test_clean_mdm_postgres.py:65-73`).
- A named, disposable "offline fixture registry authority", to square with `local-operations.md:46-47`.
- Whether the engine will offer a test-mode automatic-rule policy once rules are qualified. Without one, the
  bind/create outcomes of mastering cases stay declared, not inferred.
