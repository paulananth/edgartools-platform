# Create three empty test database instances

Status: complete

Historical creation evidence from 2026-10-17 20:11 ET. Later schema
initialization and adapter deployment changed these databases; the zero-table
counts below describe creation only. Current Company readiness is tracked in
[the Company task](../../company-three-engine-readiness/issues/01-turn-on-company.md).

Operator request: create a new branch and use the data-platform skill to
create PostgreSQL, MySQL and SQL Server test instances and their databases only.

Authority: `skills/data-platform/SKILL.md`, Setup steps 3–4 at `1f1c55ed`.
The installed skill predates the current container instructions; use the
repository skill without replacing the installed copy.

Create the six named databases (`rules`, `bookkeeping`, `change_journal`,
`mdm`, `rdm`, `silver`) in each test instance. Apply no application schemas
or migrations and load no records. Keep credentials private outside Git.
Use the configured Docker context. Preserve the existing local instances.

## Checklist

- [x] Create a dedicated branch and worktree from current origin/main; verified clean starting state and base `1f1c55ed` — 2026-10-17 20:11 ET.
- [x] Check current skill instructions and existing containers/volumes for ownership conflicts; three test names and volumes were absent — 2026-10-17 20:11 ET.
- [x] Create the PostgreSQL test container, persistent volume and six empty databases; authenticated queries verified readiness and zero user tables — 2026-10-17 20:11 ET.
- [x] Create the MySQL test container, persistent volume and six empty databases; authenticated queries verified readiness and zero user tables — 2026-10-17 20:11 ET.
- [x] Create the SQL Server Express test container, persistent volume and six empty databases; authenticated queries verified readiness, Express edition and zero user tables — 2026-10-17 20:11 ET.
- [x] Verify private credential-file permissions, loopback ports, restart policies and preserved existing instances; Docker inspection and filesystem mode checks passed — 2026-10-17 20:11 ET.
- [x] Review the resulting ticket and run whitespace/overlap checks; Standards, Spec and GoF assessment below, `git diff --check` and overlap guard passed — 2026-10-17 20:12 ET.
- [x] Learning → skill: none; the current repository skill already states the required container/database workflow — 2026-10-17 20:12 ET.

## Evidence

| Engine | Container | Databases verified | User tables |
|---|---|---:|---:|
| PostgreSQL 16 | `edgartools-test-postgres` | 6 | 0 |
| MySQL 8 | `edgartools-test-mysql` | 6 | 0 |
| SQL Server 2022 Express | `edgartools-test-sqlserver` | 6 | 0 |

All use named volumes, loopback-only dynamically assigned ports and
`unless-stopped` restart policies in the existing OrbStack Docker context.
SQL Server uses `linux/amd64`. Reused the three locally available images;
no image build or provider request was needed. The three pre-existing
`edgartools-local-*` instances remain running and were not modified.

Private container credentials and per-engine connection files live under
`~/.local/share/edgartools/test-instances/{postgres,mysql,sqlserver}/`.
Each directory is mode `0700`; `container.env` and `connection.env` are mode
`0600`. Neither their contents nor database addresses belong in this ticket.
Each `connection.env` defines the six skill-named database variables for its
engine. These are administration connections for empty test databases.

No application schemas, migrations, source data or approval records were
created. The skill's application doctor was outside this database-only task:
the application executable is absent from PATH, and application schema
initialization belongs to the separate data-operations flow.

## Standards

Dedicated Codex branch/worktree; unrelated main work remains untouched.
Only this operational ticket changes in Git. Private files stay outside Git.
Live database queries provide the affected proof; no application-code tests
are required for creating empty databases.

## Spec

Created exactly three test instances using Setup steps 3–4, with the six
skill-specified databases in each. Verified all 18 databases have zero user
tables. No application setup or production deployment occurred.

## GoF

The reviewer skill is available and was read. No application code was
written or modified, so there is no code diff requiring a pattern refactor.
