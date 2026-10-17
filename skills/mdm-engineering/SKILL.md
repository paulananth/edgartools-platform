---
name: mdm-engineering
description: Change the MDM store's code or schema - the Merge Stage, its SQL functions, migrations, lookups and indexes, transactions - and choose the cheapest proof that the change is right. Use before writing or reviewing any change under the MDM code or its migrations, when a mastering run is slow or refuses work, or when deciding which proof a change needs.
---

# MDM Engineering

> Part of the **data-platform** skill set. The data skills (data-onboarding,
> refining-rules, data-quality) change rules as data; this skill is for a
> change to the MDM engine and store themselves.

It answers: **is this change to the MDM store lean, fast on a hosted
Postgres, safe to migrate, and proved by the cheapest check that proves it?**

Each rule below was learned from a failure here. The Examples section names
where.

## Hard stops

- **Design for the hosted target.** MDM, Rules and Bookkeeping run on a
  hosted, Postgres-compatible service. A local PostgreSQL 16 (in Docker) is
  for tests and Proving Runs only. Never choose a cap, a batch budget or a
  refusal to fit a local machine. Only PostgreSQL's own limits and the hosted
  service's documented ones apply.
- **Never refuse work by size.** Cut the input into batches; that divides
  work and refuses nothing. A size cap that stops a run is a defect.
- **Remove a layer rather than tune it.** When a copy, a trigger chain or a
  table makes a step slow or hard to follow, prefer the design that deletes
  it over one that speeds it up. Adding an MDM field is data or policy, not a
  schema change spread across files.
- **No table scans.** Every read is by key, through an index, except a
  table that stays a handful of rows. A test shows it.

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

Never load "everything connected" to a batch. Through one shared end, a
network of links makes every batch cost the whole network.

## Postgres: lookups and indexes

- **Look up a list of keys one index probe per key:**
  `unnest(keys) k(key) CROSS JOIN LATERAL (SELECT ... FROM t WHERE t.col =
  k.key OFFSET 0)`. The `OFFSET 0` keeps PostgreSQL from folding the probe
  into a join that reads a whole index, which it prefers on a small table and
  which grows with the store. When the lookup covers several indexed
  columns, write one branch per column under `UNION ALL`.
- **Never use `col = ANY(keys)` under an `OR`, nor an `OR` beside an
  `IN (subquery)`.** Both read the whole table.
- **Probe a GIN index one key at a time** (`@> ARRAY[k.key]`, `? k.key`),
  never with the whole list (`&&`, `?|`). Keep `fastupdate = off` on such an
  index, or every search reads its growing pending list. When code starts
  probing an existing GIN index this way, check that index's `fastupdate`
  too: binding started probing the identifier index with its list still on.
- **A PL/pgSQL function that looks rows up against a key list held in a
  variable carries `SET plan_cache_mode = force_custom_plan`.** After five
  calls PL/pgSQL may reuse a generic plan, which cannot hash the list, so
  every row is compared with every key. No other function carries the
  setting, and a session never sets it.
- **Read set-based.** A batch's reads are a few queries over its keys, never
  one query per record. Fetch what a batch needs at once, memoize what does
  not change within it, and write it back in one statement. Assume a new
  batch path does one query per row until a run at scale shows it does not:
  tests on a small or in-memory store never show it.
- **A whole read is allowed only for a table that stays a handful of rows**
  (for example, the decisions that retire a source), and its docstring says so.
- **Prove it.** A test runs each lookup with sequential scans off and checks
  that it uses its index. Another refuses a whole-list search in any MDM
  function, and a `CREATE OR REPLACE` that drops the plan setting.

## Migrations

- A schema change is a new migration file, added at the end of the
  registered list. Never edit an applied one.
- Test every migration against a **populated** table. An empty-table test
  proves nothing about what a migration exists to do.
- Postgres cannot defer a **partial** unique index. It is checked at every
  row-level update, so order and flush multi-row status changes yourself.
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
- A function that looks up or writes many keys takes them as one array, not
  one call per key.
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
| Speed | Time per batch over a whole feed: flat, not growing with the store |

Say the time of any proof over ten minutes before starting it. Stop its
containers when it ends, whatever the outcome.

## Examples

These name this repo's code and the failures each rule came from.

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
