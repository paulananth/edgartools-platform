# Evidence — hosted qualification and credential gate

Date checked: 2026-11-13. All findings are from local, read-only inspection. No production
connection, no credential value read, no write.

## 1. Hosted qualification: still deferred

| Source | Says | Date |
|---|---|---|
| `docs/specs/mdm/acceptance.md:5` | "No hosted qualification or cutover gate has passed." | file last changed 2026-10-13 (`f9e89470`) |
| `docs/specs/mdm/acceptance.md:120-121` | "The user selected local PostgreSQL for continued qualification on 2026-09-19; Snowflake qualification is deferred." | 2026-10-13 |
| `docs/specs/mdm/state-of-build.md:133-136` | "The current qualification target is **local PostgreSQL 16**. Snowflake Postgres qualification is deferred." | file last changed 2026-11-02 (`203c690c`) |
| `docs/specs/mdm/state-of-build.md:253-257` | Next step is still "qualify the identical migrations on the user-selected hosted target when requested" — i.e. not yet done. | 2026-11-02 |
| Retained measurement snapshot `~/.local/share/edgartools/load-logs/measure-prod-fast-20261112-141251-ET/report.json` | `gates.hosted_qualification = "uncleared in retained evidence"` | 2026-11-12 |
| Retained fresh check `~/.local/share/edgartools/load-logs/measure-prod-fresh-report-20261112/metadata.json` | `qualification_gate = "uncleared; retained-only"` | 2026-11-12 |

Searched for a newer approved qualification record: `grep -rln "Snowflake Postgres"` over `docs/`
and `.scratch/` in the checkout returns only the two spec files above plus agent guides and
unrelated scratch notes. The newest of them is still the deferral. **No newer record clears the
gate.**

The instance itself exists and is READY (`show-postgres-instances.json`, observed 2026-11-12
14:55:23.929 ET: `state = READY`, PostgreSQL 16, 50 GB, BURST_S). Readiness is not qualification.

## 2. Credential-rotation evidence: none found

- The only retained Snowflake-side access event is
  `~/.local/share/edgartools/load-logs/measure-prod-readonly-20261112T180117Z/query-history-reset-access.json`,
  which is itself a read-only `snowflake.account_usage.query_history` **query** whose text contains
  the string `RESET ACCESS` as a search filter. It is not a credential change.
- A search of the whole private load-log directory and the private hosted store for
  `RESET ACCESS`, `ALTER USER` and rotation records returned only that file plus unrelated
  manifest payload text. No `ALTER USER ... PASSWORD`, no `RESET` execution, no rotation record.
- `~/.local/share/edgartools/hosted-prod/create-instance.err` is **0 bytes** — no error output from
  the creation run, and no rotation trail.

**No credential-rotation evidence exists in the retained evidence.**

## 3. Do the private env files point at rotated credentials? No — they point at the same set

Fingerprinted each value in the private env files (SHA-256 prefix of the value; no value printed):

| Key | `governance.env.before-reset-20261112` (2026-11-10 21:44) | `governance.env` (2026-11-12 17:24) | `connection.env` (2026-11-10 21:42) | `worker.env` (2026-11-10 21:57) |
|---|---|---|---|---|
| `MDM_DATABASE_URL` | `45b55c830305` | `45b55c830305` | `45b55c830305` | `45b55c830305` |
| `MDM_MIGRATION_DATABASE_URL` | `bd361378f750` | `bd361378f750` | `bd361378f750` | — |
| `MDM_APPLICATION_ROLE` | `3ee87090645b` | `3ee87090645b` | `3ee87090645b` | `3ee87090645b` |
| `BOOKKEEPING_DATABASE_URL` | `ece336e4fc6a` | `ece336e4fc6a` | `ece336e4fc6a` | `ece336e4fc6a` |
| `CHANGE_JOURNAL_DATABASE_URL` | `3fe2f2be5ac9` | `3fe2f2be5ac9` | `3fe2f2be5ac9` | `3fe2f2be5ac9` |
| `SILVER_DATABASE_URL` | `2e2eca0e9867` | `2e2eca0e9867` | `2e2eca0e9867` | `2e2eca0e9867` |
| `RULES_DATABASE_URL` | `674fd73eafb8` | `674fd73eafb8` | `a7c913e6bc24` | `a7c913e6bc24` |
| `RDM_DATABASE_URL` | `5095df63e6ad` | `5095df63e6ad` | `5095df63e6ad` | `5095df63e6ad` |

Findings:

- Every credential-bearing value in `governance.env` is **byte-identical** to the pre-reset copy
  from 2026-11-10 21:44. The file's later modification time (2026-11-12 17:24) reflects edits to
  *non-credential* keys only: `MDM_REGISTRATION_DATABASE_URL` and
  `RULES_MDM_ACTIVATION_DATABASE_URL` were added, both sharing fingerprint `8ebb5244a340`.
- `connection.env` and `worker.env` carry the same `MDM_DATABASE_URL` and `MDM_APPLICATION_ROLE`
  fingerprints as the pre-reset file. `RULES_DATABASE_URL` differs between
  `governance.env`/`connection.env` and `worker.env` — a rules-store difference, not a credential
  rotation.
- Therefore **the current private environment points at the same, unrotated credential set** that
  was live when the exposed read occurred.

## 4. Consequence

Both gates stay closed:

- hosted qualification: **uncleared** (deferral stands, no newer record);
- credential rotation: **not evidenced**, and the fingerprints show the live env files still carry
  the unrotated set.

**The measurement is retrospective-only.** No new production source load may be submitted, and no
MDM/Postgres connection may be made with these credentials. The report is built from retained
evidence, exactly as the retained 2026-11-12 snapshot was.

The credential-rotation prerequisite is an operator action with its own procedure, not a
measurement decision; it is listed as out of scope on the map.
