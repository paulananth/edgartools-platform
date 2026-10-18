---
name: mdm-engineering
description: Engineer database-agnostic MDM merge logic and its storage adapters for PostgreSQL, MySQL or SQL Server Express. Use before writing or reviewing MDM code or migrations, qualifying native cross-reference lookup, adding database support, diagnosing a slow or refused mastering run, or choosing its proof. Data-operations applies silver DDL.
---

# MDM Engineering

> Part of the **data-platform** skill set. The data skills (data-onboarding,
> refining-rules, data-quality) change rules as data; this skill is for a
> change to the MDM engine and store themselves.

It answers: **is this change to the MDM store lean, fast on the engine it
runs on, safe to migrate, and proved by the cheapest check that proves it?**

The operator chooses PostgreSQL, MySQL or SQL Server Express. This skill owns
one Merge Stage contract across those engines and the engineering needed to
support their storage differences. Its executable adapter persists prepared
effects without interpreting entity or source policy. The application's
native store commands remain PostgreSQL-only; the skill adapter does not
replace their configuration or run-control workflow. A silver table spec is applied by
[data-operations](../data-operations/SKILL.md).

Adapter implementation belongs under this skill's `scripts/`, with
[database_adapter.py](scripts/database_adapter.py) as its entry point.
Entity/source names and field policies arrive as data from the shared engine;
the adapter contains no domain branches or application imports. Read
[Storage adapter contract and execution](references/storage-adapters.md)
before provisioning, migrating, applying prepared effects or reviewing the
boundary. Apply its GoF review before recommending a change and again
against the resulting work.

Each rule below was learned from a failure here. The Examples section names
where.

## Database-agnostic merge logic

**Compute once in programs; persist through the selected engine.** Configured
matching, identity replay, source-revision folding, field/profile survivorship,
classification and relationship/hierarchy computation belong to the shared
Rust/Python engine. Generic configured computation belongs in Rust through
Python callers; custom functions, coordination and database clients remain
Python. Keep one policy interpretation and one merge algorithm for all
engines. A dialect branch must not change which masters bind, which claims
win, which links exist or which records wait or are rejected.

Storage adapters own connections, types, SQL compilation, indexed retrieval,
schema migrations, grants and transaction/concurrency primitives. Use
[sql-writer](../sql-writer/SKILL.md) for portable models and statements;
isolate necessary engine-specific storage code behind the same operations.
Business merge rules do not belong in separate stored-function copies for
each database. Keep exact integers and decimals, null/empty distinctions,
timestamp precision, ordering and canonical publication bytes consistent
across adapters; preserve already-stored bytes and their hashes.

**Prepare in code; validate and commit at the destination.** The selected
database must authoritatively enforce current-state freshness, uniqueness,
lease/fence ownership, authorization and atomic writes of proposals, effects,
history, checkpoints and publication intent. Program prechecks alone cannot
protect competing writers. Each adapter must provide equivalent transaction
and rollback behavior using that engine's supported mechanisms. Keep the
existing restricted function API until its replacement proves the same
enforcement and grants; removing a PostgreSQL guard is not a portability fix.

When a selected engine is refused, identify the missing storage operation or
migration against the shared contract. Reuse the same merge logic and
versioned policy. Keep storage implementation in the skill and domain
computation with its existing owner. Distinguish the helper's prepared-effect
capabilities from missing application integration, configuration registration
or run-control operations. Report unsupported operations until qualified;
changing a skill, deleting a dialect check or creating empty tables does not
implement the adapter.

### Prove the same behavior on every engine

For database-support work, run the same pinned fixtures, contracts and policies
for every affected kind and source through real PostgreSQL, MySQL and SQL
Server test instances with restricted runtime roles. Compare identity decisions, field
and profile winners, relationship history, waiting/rejected outcomes and
publication content; normalize independently allocated IDs only through a
verified identity crosswalk. Exercise exact numeric and temporal boundaries,
unchanged replay, interrupted recovery, rollback, conflicting concurrent
writers and stale leases. Verify each engine's migrations, grants and indexed
lookup plans as well. An engine is supported only after its full caller path
passes; compilation, connectivity and PostgreSQL-only tests are insufficient.

## Hard stops

- **Design for the hosted target.** MDM, Rules and Bookkeeping run on the
  hosted engine that environment uses: PostgreSQL, MySQL, or SQL Server
  Express. A local container of that same engine is for tests and Proving
  Runs only. Never choose a cap, a batch budget or a refusal to fit a local
  machine. Only that engine's own limits apply. SQL Server Express's 10 GB
  per database is an edition limit: report it, and do not add a batch cap to
  stay under it.
- **Never refuse work by size.** Cut the input into batches; that divides
  work and refuses nothing. A size cap that stops a run is a defect.
- **Remove a layer rather than tune it.** When a copy, a trigger chain or a
  table makes a step slow or hard to follow, prefer the design that deletes
  it over one that speeds it up. Adding an MDM field is data or policy, not a
  schema change spread across files.
- **No table scans.** Every read is by key, through an index, except a
  table that stays a handful of rows. A test shows it.

## Cross-reference completion

MDM owns source-record identity bindings, canonical master redirects and
lookup-only cross-references. Keep those roles distinct: a cross-reference
finds records but does not establish sameness. Binding/merging goes through
approved matching rules or authorized steward decisions, with the kind's
Identifier Contract enforced.
RDM owns versioned code-set crosswalks; they do not resolve source records to
master entities. Use the packaged
[identity/cross-reference guidance](../data-modeling/SKILL.md#3-identity-or-cross-reference).

Onboarding/refining-rules maps lookup-only namespaces through the Dataset
Contract's `adapter.cross_references` and, where required, `adapter.cross_reference_formats`,
separately from `identifiers`. MDM engineering owns their storage, indexed
retrieval, provenance and per-engine integration; data-operations applies the
qualified migration. Retain cross-references with the source readings and
derive their current lookup from that authority, without a second write path.

The native PostgreSQL implementation exposes `mdm.cross_reference` and indexed
`mdm.cross_reference_lookup(namespace,value)`. A lookup returns the source and
record, reading/batch provenance, original bound entity and current canonical
entity. Waiting records can be found with no bound entity. Preserve multiple
records sharing one lookup value; that equality alone joins nothing.

For each selected engine and affected contract, prove mapping/formatting,
indexed lookup, waiting/unbound results, canonical lookup after a merge,
correction/retirement behavior under its publication contract, retained
provenance, migration/grants and unchanged replay. Verify changes commit with
the owning MDM readings and identity state. Storing an opaque field or passing
another engine's tests does not qualify native cross-reference retrieval.
When inputs carry no cross-references, record the profiling evidence for that
scope instead of inventing a mapping or silently omitting the check.

## The Merge Stage: each batch costs only what its records touch

**Match first.** The batch's records are matched outside the save: each
identifier is looked up through its index; a record joins the master it
names, or a new master is proposed. Name rules follow, only where no
identifier exists. The save then checks the proposal again under the save
lock, and a proposal another run has overtaken is proposed again (a few
tries, then the run stops).

**Then read only what the batch touches,** by key, through an index:

1. **The affected masters:** each record of the batch, and each record or
   master a steward decision in the batch names, with the decisions that bind
   or merge them, until each identity is whole. Links are not followed.
2. **The links those masters start:** every source record of their members,
   and the source records their stored links cite. A plain link's far end is
   read as it is stored, never replayed.
3. **The links into a master whose identity changed** (new, merged, or a
   changed status, kind or profiles): every source record that links to its
   records. A new record for an existing master changes none of these, so the
   links of its other masters are never read.
4. **A hierarchy whole:** a parent-type link walks its stored chain up and
   down, so cycles, a second parent and ultimate parents see all of it. Plain
   links never walk.

A stored row outside this scope is neither rewritten nor retired. Each
affected master is recomputed alone and written only if it changed; reviews
cover only the affected masters, records and links. The proposal and the
batch are saved in one transaction.

**A waiting record is looked at again only when it is applied again.** A
record whose matching rule waits for a master another feed creates later in
the same pass stays waiting in that pass. A run that loads several feeds
therefore applies its passes until one changes nothing, and reports how many
it took; the last pass must change nothing.

Never load "everything connected" to a batch. Through one shared end, a
network of links makes every batch cost the whole network.

## Lookups and indexes

On every engine, a list of keys is one index seek per key. A plan that scans
the table, or reads a whole index, is a defect. Several indexed columns are
separate seeks, never one `OR` across them. Reads are a few queries over the
batch's keys, never one query per record. A whole read is allowed only for a
table that stays a handful of rows, and its docstring says so. A test shows
the seek. Integer columns that count records are 64-bit (`BIGINT`).

**PostgreSQL.** Look up with `unnest(keys) k(key) CROSS JOIN LATERAL (SELECT
... FROM t WHERE t.col = k.key OFFSET 0)`. The `OFFSET 0` keeps the planner
from folding the probe into a join that reads a whole index. Several columns
are one branch each under `UNION ALL`. Do not use `col = ANY(keys)` under an
`OR`, or an `OR` beside an `IN (subquery)`. Probe a GIN index one key at a
time (`@> ARRAY[k.key]`, `? k.key`), never with the whole list (`&&`, `?|`),
and keep `fastupdate = off`. A PL/pgSQL function that holds the key list in a
variable carries `SET plan_cache_mode = force_custom_plan`. No other function
carries it, and a session never sets it. A test turns sequential scans off
and refuses a whole-list search or a `CREATE OR REPLACE` that drops the plan
setting.

**MySQL.** Join the key list as its own derived table and require a `ref` or
`eq_ref` access in `EXPLAIN`. A scan (`ALL`) fails the test. Do not look an
identifier up with JSON containment. MySQL has no `plan_cache_mode`; keep the
key list in the statement that is planned for that list, not in a reused
prepared statement whose plan was chosen for a different list size.

**SQL Server Express.** Join the key list as a table-valued parameter or a
temporary table and require an index seek in the plan. A scan fails the test.
A statement whose key-list size changes enough to pick a bad cached plan uses
`OPTION (RECOMPILE)` on that statement only. Do not put it on every procedure.

## Migrations

- A schema change is a new migration file, added at the end of the
  registered list. Never edit an applied one.
- Test every migration against a **populated** table. An empty-table test
  proves nothing about what a migration exists to do.
- PostgreSQL cannot defer a **partial** unique index, and SQL Server checks a
  filtered unique index at each row. Order and flush multi-row status changes
  yourself. MySQL has no partial unique index; enforce that rule in the same
  ordered write, and do not invent a second table to imitate the index.
- Guard a privileged `GRANT` with an "already satisfied" check, so a rerun by
  a role without the admin option does not fail.
- A migration is applied explicitly. A deploy that carries a new migration is
  incomplete until the migration has run.

## Writes and transactions

- Commit only when the work a checkpoint claims is itself durable, and roll
  staged state back on failure. A database session commits nothing on its
  own, and a logged "succeeded" is not a durable write.
- Write only the rows that changed, set-based, not one row at a time in a
  loop.
- A storage operation that looks up or writes many keys takes a bound key
  collection, not one call per key. Each adapter uses its engine's supported
  bulk parameter or temporary-table mechanism.
- A run reads what it started with. Anything the store registers anew while
  the run is part way through (a source's mapping today) is chosen once when
  the run first starts, kept in its frozen scope (`mdm.run.scope`), and read
  back on every later call and resume, never resolved again per batch. The
  commit still checks it.

## Choose the cheapest proof

| The change | The proof |
|---|---|
| Any code, a migration, a rules or data file | The affected tests, locally, and CI (`AGENTS.md`, "Tests and CI") |
| A rule upstream of MDM (a source extract, a combine step) | Compare the changed step's output over a capture, and the combined output on one bundle. Equal combined bytes mean everything downstream is unchanged |
| The Merge Stage, matching rules, a Dataset Contract, a worker, Bookkeeping | A Proving Run on a pinned cohort, and the full installed proof on an empty store: every count as before, a killed worker resumes, the second pass changes nothing |
| A storage adapter or a change claimed to work across databases | The shared per-engine behavior checks above for every affected kind and source; preserve restricted-role, transaction and recovery guarantees |
| Speed | Time per batch over a whole feed: flat, not growing with the store |

Say the time of any proof over ten minutes before starting it. Stop its
containers when it ends, whatever the outcome.

## Examples

These name this repo's code and the failures each rule came from.

- **Database portability:** use the same pinned Company and Person fixtures
  and policies on PostgreSQL, MySQL and SQL Server, plus every other affected
  kind/source, applying the qualification checks above. These are concrete
  test cohorts, not limits on the shared merge algorithm.
- **Code:** the Merge Stage is `edgar_warehouse/mdm/clean/merge.py`, and what
  a batch reads is `edgar_warehouse/mdm/clean/scope.py`; the
  input cut is `edgar_warehouse/mdm/clean/limits.py` (1,000 records and
  1 MiB a batch); the migrations are registered in
  `edgar_warehouse/mdm/clean/store.py` (`MIGRATIONS`).
- **Tests that hold the rules:**
  `tests/integration/test_clean_plan_cache_postgres.py` (plan setting, no
  whole-list search), `tests/integration/test_clean_lookup_indexes.py`
  (every lookup uses its index), `tests/mdm/test_clean_limits.py` (no size
  cap in any function).
- **No size refusal** (rebuild ticket 74): a 10,000-record closure cap and a
  16 MiB request cap, chosen for a local machine, stopped the ownership
  Proving Run, whose insider network was one connected group.
- **Record by record** (rebuild ticket 77): without the cap, every batch
  replayed the whole insider network (23 batches in 60 minutes); merging only
  the masters a batch touches made batch times flat over the full Person feed.
- **Join the keys** (profiling ticket 07): at 2,229 keys a whole-list GIN
  search took 12 to 21 s, and one key at a time 14 to 18 ms for all of them.
  A generic plan took 5.2 s against 0.8 s for a custom one.
- **Remove a layer** (operator, 2026-09-26): the Merge Stage writes and reads
  the dated master table directly, instead of copying rows between tables.
- **Cheapest proof** (operator, 2026-10-13): a source extract column trim
  already shown equal over 7,000 documents needed no 45-minute proof.
- **The full installed proof** for the Company population:
  `.planning/workstreams/whole-source-census/installed_proof.py` (its
  docstring has the command; about 28 minutes; 6,414 Companies, 3,052 GLEIF
  bindings).
