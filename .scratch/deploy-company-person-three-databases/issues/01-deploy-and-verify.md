# Deploy Company, Person and MDM merging on three test servers

Status: **adapter implemented and fixture-qualified on all three selected
servers; operational source deployment remains incomplete.** Review PR:
[#1073](https://github.com/paulananth/edgartools-platform/pull/1073).

The operator authorized executable adapter code inside the skill and required
it to remain decoupled from Company, Person and other domain names. This
supersedes the earlier instructions-only answer. The adapter's implementation
is entirely under `skills/mdm-engineering/scripts/`; application modules and
CLI commands are unchanged. Shared merge computation supplies opaque prepared
effects. No source approval or activation is implied by fixture qualification.

## Checklist

- [x] Inspect current main, runtime ownership, skills and prior evidence; dedicated branch/worktree and base `a4516ff6` verified — 2026-10-18 07:33 ET.
- [x] List and authenticate to the three selected test servers and six databases on each; preserve existing local containers and private connections — 2026-10-18 07:33 ET.
- [x] Verify the existing native PostgreSQL deployment boundary: 21 MDM migration checksums match; restricted operational runtime; three configuration drafts without proof/approval — 2026-10-18 07:33 ET.
- [x] Qualify the existing full native Company/Person fixture on the selected PostgreSQL server in an isolated database; one test passes in 2.44 seconds, temporary database and role removed — 2026-10-18 07:33 ET.
- [x] Document and test the native MySQL/SQL Server initialization refusals; five stores on each still require PostgreSQL 16 — 2026-10-18 07:33 ET.
- [x] Preserve the initial instructions-only contract in commits `677f4953` and `94a54a2f`; latest operator ruling supersedes that implementation boundary — 2026-10-18 08:41 ET.
- [x] Implement domain-independent models, exact-byte persistence and engine-specific atomic capabilities within the owning skill; seven genericity checks and standalone packaged entry point pass — 2026-10-18 08:41 ET.
- [x] Enforce restricted runtime permissions, captured generation/version/checkpoint conflicts, history, immutable evidence, leases/fencing and publication receipts; all 19 behavior cases pass on each engine — 2026-10-18 08:41 ET.
- [x] Prove shared identity/survivorship/relationship outputs for Company and Person plus unrelated opaque fixture data on every selected engine; verify rollback, concurrent writers, restart, replay, migration rerun and indexed lookup plans — 2026-10-18 08:41 ET.
- [x] Install the skill adapter persistently on each selected test server; ten owned tables, two fixture batches, six current/history objects, five evidence records and three physically verified publications per engine; populated migration rerun installs nothing — 2026-10-18 08:41 ET.
- [x] Update skill instructions and CI matrix; wheel contains all six skill resources byte-for-byte and extracted standalone helper runs outside the checkout; skill validator, Ruff and whitespace checks pass — 2026-10-18 08:41 ET.
- [x] Review final work under Standards, Spec and GoF; evidence and limits below — 2026-10-18 08:41 ET.
- [x] Update and push review PR [#1073](https://github.com/paulananth/edgartools-platform/pull/1073) around the executable adapter; commit `bb068c26`; CI and the three-engine matrix are running, with results tracked on the PR checks — 2026-10-18 08:44 ET.
- [ ] Deploy operational Company and Person configuration on PostgreSQL: existing drafts lack genuine proof/approval and required published reference versions. Fixture results do not supply release authority.
- [ ] Deploy operational Company and Person pipelines on MySQL: native Rules, Bookkeeping, reference and application Store integration remain unimplemented; this prepared-effect adapter is not that integration.
- [ ] Deploy operational Company and Person pipelines on SQL Server: native Rules, Bookkeeping, reference and application Store integration remain unimplemented; this prepared-effect adapter is not that integration.
- [x] Learning → skill: `references/storage-adapters.md` documents executable ownership, exact JSON bytes, frozen preparation generation, destination enforcement, restricted grants, qualification scope and the native integration boundary — 2026-10-18 08:41 ET.

## Selected databases and physical results

| Test server | Engine | Adapter behavior tests | Persistent adapter fixture state |
|---|---|---|---|
| `edgartools-test-postgres` | PostgreSQL 16 | 19 passed, 9.69 seconds | Migration 1, generation 2, six objects, three verified publications |
| `edgartools-test-mysql` | MySQL 8 | 19 passed, 15.69 seconds | Migration 1, generation 2, six objects, three verified publications |
| `edgartools-test-sqlserver` | SQL Server 2022 Express | 19 passed, 69.98 seconds | Migration 1, generation 2, six objects, three verified publications |

Each adapter uses its selected server's existing `mdm` database and a separate
restricted runtime principal. Its `skill_merge_*` objects coexist with native
schemas. Existing data and all six pre-existing test/local containers remain.
Public records contain counts and invented examples only. Credentials,
connection addresses, exact fixture envelopes and verification logs remain
under the private `~/.local/share/edgartools/test-instances/` directory.

The persistent results contain two Companies and two Persons computed with
the existing Rust identity engine, shared Python survivorship and typed
relationship projection, one resulting relationship, and one unrelated
opaque object. Independent readback confirms identical stored object and publication bytes on all three engines. Temporary proof databases and principals are absent on all three servers. Three publication
envelopes per engine were written to private local files, independently read
back, hashed and acknowledged through fenced runtime capabilities. All outbox
rows are verified. A repeated batch returns its original generation without
new writes. Re-running the populated migration preserves state.

The 19 cases cover exact large integers/decimal spelling/Unicode/null/empty
and temporal boundary bytes, current/history changes, unchanged replay,
historical replay after later generations, batch collisions, frozen pins,
stale generation/checkpoint/object versions, concurrent saves, denied direct
DML/schema bypasses, expired/reclaimed writer and publication fences, verified
receipts, actual mid-save database failure with complete rollback, restarted
caller recovery, immutable evidence, pending/checksum/security drift,
commit-time lease enforcement, indexed lookup plans and complete 805-key
chunked reads. Shared computation is exercised for both requested kinds;
storage treats types, fields and policy documents as opaque data.

The tests use isolated disposable databases and restricted principals on the
selected servers, with cleanup in `finally`. CI creates one disposable real
server per matrix job, has a 15-minute deadline and an unconditional server
cleanup step. No prerequisite is silently skipped. Each local pytest process
is bounded below five minutes and uses testmon.

## Standards

Implementation changes are confined to the owning skill; supporting tests,
CI and this ticket accompany them. Application/CLI code and other runtimes'
WIP are preserved. Privileged grants check existing effective rights before
issuing GRANT, and broad/direct-write runtime privileges are refused.
Migration readback verifies checksum, columns/types, keys, indexes, engine
storage and capability source/security. Runtime uses only bound, restricted
destination capabilities for writes. Public errors contain fixed refusal
codes rather than database parameters. The wheel's six exact skill resources
and extracted helper were verified; validator, seven genericity cases, Ruff
and whitespace checks pass. Overlap guard passes.

## Spec

The executable adapter is generic, skill-owned and physically tested on all
three requested engines. It stores prepared shared merge results and enforces
authoritative atomic state transitions at the destination. It introduces no
second matching, identity, survivorship or relationship algorithm.

Native MDM/RDM/Bookkeeping/Change Journal/Silver initialization still refuses
MySQL and SQL Server with each store's existing `requires PostgreSQL 16`
message. Existing operational PostgreSQL Rules drafts have no proof/approval;
MDM has no activated operational datasets/policies. Native integrations and
operational activation are the three unchecked deployment items above. This
adapter qualification must not be reported as complete source deployment.

## GoF

**Overall: keep the small Adapter seam; no additional hierarchy is justified.**
`gof-refactor-reviewer` is available and was applied before implementation and
against the final change, including its smell/cost guidance. History examined:
`mdm/clean/store.py`, `merge.py`, and the recent selected-engine skill changes.
The concrete problem is three incompatible storage/transaction/security APIs;
it is not three domain algorithms.

`database_adapter.py:223` exposes one prepared-effect interface;
`adapter_model.py:24` defines one neutral logical schema;
`adapter_sql.py:272` builds the four operations from one sequence with localized
vendor syntax. Adding a domain changes caller data and no adapter code.
Adding an engine requires measured SQL/security/version qualification, a real
cost that the interface cannot erase. Adapter adds a debugging hop and has
limited fidelity to the native Store contract, explicitly documented. Bridge,
Strategy subclasses and a second Merge Stage would add indirection without
measured benefit. No further structural refactor recommended.

A final correctness review found that defaulting the save to the latest
generation could silently repin stale prepared work. Generation is now a
required captured input; the real-database regression refuses overtaken work
on all three engines. PostgreSQL deferred commit checks protect delayed direct
SQL callers; MySQL/SQL Server refuse ambient transactions. The test expires a
real lease instead of bypassing that boundary with owner updates.
