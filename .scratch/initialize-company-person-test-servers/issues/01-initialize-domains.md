# Initialize Company and Person on the three test servers

Status: incomplete — PostgreSQL schemas and draft configuration initialized;
MySQL and SQL Server require missing runtime support.

Historical initialization result from 2026-10-17 20:20 ET. The generic
skill-owned storage adapter was subsequently merged in #1073, separately
from the native store protocols refused below. The operator now requests
Company first, with Person deferred; use
[the Company task](../../company-three-engine-readiness/issues/01-turn-on-company.md)
for the remaining native integration, qualification and activation work.

Operator request: initialize Company and Person on the PostgreSQL, MySQL and
SQL Server test servers using only skills.

Scope: the existing `edgartools-test-*` containers. Follow data-platform,
data-operations and its SQL-writer reference. No application-code changes,
provider requests or source loads. Preserve unsupported-engine refusals as gaps.

## Checklist

- [x] Inspect live branch, containers, skills and command capabilities; fresh branch/worktree at `c62bce95`, current CLI built and help checked — 2026-10-17 20:20 ET.
- [x] Initialize supported PostgreSQL store schemas with restricted runtime roles; six runtime logins and one non-login approval role verified without elevated privileges; 35 migration checksums independently matched the current checkout — 2026-10-17 20:20 ET.
- [x] Save Company and Person source configurations and their shared platform policy as three drafts through `rules save`; readback confirmed three drafts, zero approvals and zero active versions — 2026-10-17 20:20 ET.
- [ ] Complete Company and Person operational initialization on PostgreSQL: genuine qualification/release evidence, published pinned reference versions and supported approval/activation remain outstanding. No source run or activation was authorized by this schema-initialization request.
- [ ] Initialize Company and Person on MySQL: blocked by the five store commands' PostgreSQL-only runtime requirements; no portable store model or supported equivalent merge functions exist in the skills.
- [x] Verify MySQL connectivity and record all five exact store-command refusals; six databases still contain zero user tables — 2026-10-17 20:20 ET.
- [ ] Initialize Company and Person on SQL Server: blocked by the five store commands' PostgreSQL-only runtime requirements; no portable store model or supported equivalent merge functions exist in the skills.
- [x] Verify SQL Server connectivity and record all five exact store-command refusals; six databases still contain zero user tables — 2026-10-17 20:20 ET.
- [x] Independently verify each engine's resulting schema/domain state; readbacks and PostgreSQL doctor passed, counts and blockers below — 2026-10-17 20:20 ET.
- [x] Review Standards, Spec and GoF; whitespace and overlap checks passed — 2026-10-17 20:21 ET.
- [x] Learning → skill: none; data-operations and SQL-writer already describe these unsupported engines/functions and require reporting the runtime gap — 2026-10-17 20:21 ET.

## Findings

The [data-operations skill](../../../skills/data-operations/SKILL.md) states:
"The commands below run on PostgreSQL 16. On MySQL and SQL Server Express they
refuse." It directs use of SQL-writer for portable tables, while PostgreSQL
function bodies stay unapplied. [SQL-writer](../../../skills/sql-writer/SKILL.md)
explicitly excludes PL/pgSQL, JSONB operators, advisory locks and partial/GIN
indexes. The MDM migrations depend on those constructs and have no portable
SQLAlchemy store model to compile. No handwritten replacement store DDL was
invented, and no unsupported command was silently bypassed.

Authenticated connections to both other engines succeeded. Each returned these
exact capability refusals, before applying store DDL:

| Store | Refusal on both MySQL and SQL Server |
|---|---|
| MDM | `MDM requires PostgreSQL 16` |
| RDM | `RDM requires PostgreSQL 16` |
| Bookkeeping | `Bookkeeping requires PostgreSQL 16` |
| Change Journal | `Change Journal requires PostgreSQL 16` |
| Silver | `Silver requires PostgreSQL 16` |

## PostgreSQL evidence

| Store | Verified migrations | Base tables |
|---|---:|---:|
| MDM | 21 | 23 |
| RDM | 2 | 9 |
| Bookkeeping | 6 | 5 |
| Change Journal | 2 | 1 |
| Silver | 1 | 1 |
| Rules | 3 | 1 |

MDM's entity-kind constraint accepts both Company and Person. Restricted
connectivity passed and the doctor returned `ok: true`. Existing source
configuration was saved using the descriptive version
`company-person-2026-10-17.test-initialization`; the platform policy remains the
existing common policy rather than a newly invented Company/Person-only policy.

Independent readback: three Rules drafts, zero active versions, zero MDM
entities, zero published RDM versions, zero Journal events, zero registered
silver specs. Company pins a published reference version that is not present
in this empty RDM store. These counts prove schema/draft initialization only;
they do not establish operational sources or qualified mastering.

## Private evidence and recovery

Per-engine command logs and readback results are under
`~/.local/share/edgartools/test-instances/<engine>/domain-initialization/`.
PostgreSQL's `runtime.env` there holds restricted connections and
`roles.env` holds generated role passwords. Both files are mode `0600` in a
mode `0700` directory. Migration connections remain in the existing private
`connection.env`. No credential or database address is included here.

All three requested test containers remain running with their persistent
volumes. The pre-existing local instances were not altered. PostgreSQL's
completed migrations and drafts remain available for subsequent qualification.
No source records, synthetic proving runs or invented approval evidence were
loaded to make an unsupported domain appear operational.

## Standards

Fresh dedicated Codex branch/worktree. Only this ticket changes in Git.
Current-checkout commands own all store DDL. Dependencies were installed with
uv; temporary MySQL and SQL Server drivers were added only to this worktree's
environment. No application code changed, so live migration/connectivity and
independent checksums/counts provide the affected proof without a test suite.

## Spec

The requested Company/Person setup is partial. PostgreSQL has the six schemas
and three draft configuration documents. MySQL and SQL Server retain their
six empty databases because their store implementations are unsupported. The
unchecked checklist items above remain outstanding and are not completed by
a successful PostgreSQL doctor check.

## GoF

The GoF reviewer is available and was read earlier in this session. There is
no application-code diff to refactor or review; no design pattern was added.
