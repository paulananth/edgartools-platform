---
name: mdm-engineering
description: Engineer database-agnostic MDM merge logic and its storage adapters for PostgreSQL, MySQL or SQL Server Express. Use before writing or reviewing MDM code or migrations, qualifying native cross-reference lookup, adding database support, diagnosing a slow or refused mastering run, or choosing its proof. Data-operations applies silver DDL.
---

# MDM Engineering

Work lean: check each step against [the seven wastes](../data-platform/SKILL.md#the-seven-wastes) and drop what adds no value.

> Part of the **data-platform** skill set. The data skills (data-onboarding,
> refining-rules, data-quality) change rules as data; this skill is for a
> change to the MDM engine and store themselves.

It answers: **is this change to the MDM store lean, fast on the engine it
runs on, safe to migrate, and proved by the cheapest check that proves it?**

The operator chooses PostgreSQL, MySQL or SQL Server Express. This skill owns
one Merge Stage contract across those engines and the engineering needed to
support their storage differences. Its executable adapter persists prepared
effects without interpreting entity or source policy. The application's
native owner migration installs governed registry storage on PostgreSQL and
MySQL. Normal saves, readers and worker recovery have separate selected-engine
qualification gates; complete support requires the full installed caller matrix. Read [governed owner installation](references/storage-adapters.md#governed-owner-installation)
before installing or recovering that registry. A silver table spec is applied by
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

**Configured vocabulary lives once, in RDM, read by Rust.** A vocabulary MDM
runs by (the relationship types, ticket 132) is an RDM code set the policy
pins, each entry a code whose properties are its rules; one Rust module reads
the pinned rows and holds the one check, called at registration and before
every calculation. Python only carries rows to it and its error back. No code
copy, no default for a missing entry: a policy pinning none has no entries,
so what would use one goes to review.

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

### Search candidate completeness

Prove candidate retrieval as well as ranking. Database word indexes differ in
minimum/maximum token length, stop words, punctuation and negative-only queries;
a shared ranker cannot recover rows its index omitted. Qualify short and stop
words alone and with other terms, quoted phrases, exclusions, alternatives and
compound boundaries through the normal caller on each selected engine. Keep
positive searches indexed and scope negative-only complements to the requested
version. A derived-index upgrade must preserve published content and pins,
revoke runtime writes during interrupted DDL, recover on retry and refresh from
authoritative content before approval freezes it.

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

Decided (operator, 2026-10-25, ticket 138): the cross-reference becomes the
one table of every identifier, each row the master id, the identifier kind,
the value, matching or lookup only, the source, first and last seen. Built
for one kind first (switched on 2026-10-26): a record may carry a list of values
for one kind; the Merge Stage looks up every matching value: none mints, one
binds, two consolidate automatically where the rule says so (below). The one
table for the other kinds is still to build; until then the rest of this
section holds.

**What a matching rule does with several masters is data on the rule.**
`on_several: merge` merges the masters a record's values reach, the oldest
surviving, only by an identifier whose Identifier Contract states
`consolidates: true` (an identifier that names one thing however it is
listed; never a national number two masters may share). `on_conflict:
first` binds to the one master the rule's value reaches and lists the
values another master holds as the bind's `withheld`. Otherwise: review. A
record in review merges nothing.

**A filer's copy of an identifier it does not issue is lookup only.** A
source the Identifier Contract does not name in `sources` maps it as a
cross-reference; a matching rule naming that source (`on_no_match: wait`;
a rule open to every source never does) reads the cross-reference, finds the master holding the value and binds to
it, but the value is never minted, projected or counted as held, and the
rule may not merge (activation refuses it). A value two masters hold reaches
both, so the record's own `first` identifier still settles the conflict.
Registration refuses a cross-reference only on a namespace the dataset
itself issues (ticket 138, Design 5).

**A rule's merge** is a `merge` decision (`actor: rule:<id>@<version>`, no
survivor named). It names every live merge either side rests on
(`depends_on`), stored or made earlier in the batch; replay applies a merge
after those it depends on, even at the same time. The planner reads the
stored merges, Match Exclusions and their reversals about the masters
reached once per batch; the save repeats that read under the lock, and a
change makes the proposal stale. An excluded pair goes to review.

**Which values a record gives its master** is decided in one place,
`edgar_warehouse/mdm/clean/withholding.py`. Every reader that answers
"which master holds this value" or "which values does this master hold"
runs its own query, then asks it: both stores' holder lookups, the portable
carrier read, name matching's held values, the agent lookup, the planner's
re-delivered records and the master projection. A new rule about which
values count changes that module, never the seven readers (ticket 138 had
to edit all seven twice before it existed). The lookup index keeps a
withheld value; the readers drop it.

MDM owns source-record identity bindings, canonical master redirects and
lookup-only cross-references. Keep those roles distinct: a cross-reference
finds records but is never a master's identifier and never merges masters. Binding/merging goes through
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

The governed reader resolves cross-references through indexed source-record
references and their retained readings. A lookup preserves the source and record,
reading/batch provenance, original bound master and current canonical master.
Waiting records can be found with no bound master. Preserve multiple records
sharing one lookup value; that equality alone joins nothing. A retired native
routine or view is not a normal reader interface.

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

**A lookup over current masters is an index passed as data** (ticket 138).
`master_index.py` owns what every such lookup needs: a retained summary per
master, per-generation coverage, the batch's changes once coverage is
complete, and the resumable owner rebuild. A lookup gives an `Index`: its
family, the pin of its configuration, `derive` (a master's body to its
envelope, summary and groups) and `check` (a retained summary back to the
groups it wrote). Name search (`master_search.py`) and the configured detail
lookup (`detail_lookups.py`) are two; a third adds an `Index` and its reader,
never a copy of the coverage or rebuild. A changed engine catalog reaches a
store only through the owner's `mdm migrate`, and a new lookup over stored
masters needs its rebuild before readers accept it.

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
- A populated native store does not migrate to governed storage; convert it
  with `edgar-warehouse mdm convert-native` (owner only;
  `NATIVE_MDM_DATABASE_URL` the native store, `MDM_DATABASE_URL` a fresh
  governed one). It applies each saved batch's command again, oldest first, so
  every master keeps its id; it carries the approved policies and Dataset
  Contract readings, and a rerun skips the saved batches. Back up first, rename
  the native database (`mdm_native`), make it read-only and revoke the
  application roles' connect, then install the fresh store under the old name.
  The command's checks (the same masters, every record's binding, no decision
  lost) fail it with exit 1.
- A governed store keeps each batch's whole request, which can be a hundred
  MB or more after a large load or a conversion. A whole-store check reads the
  current records (`iter_type`), never consumer pages: a consumer page reads
  each master with its batch's request, once a row.

## Writes and transactions

- Commit only when the work a checkpoint claims is itself durable, and roll
  staged state back on failure. A database session commits nothing on its
  own, and a logged "succeeded" is not a durable write.
- Write only the rows that changed, set-based, not one row at a time in a
  loop. An `executemany` UPDATE can still be a driver loop: count actual
  statement executions to prove one write per batch and none on unchanged
  retries.
- A storage operation that looks up or writes many keys takes a bound key
  collection, not one call per key. Each adapter uses its engine's supported
  bulk parameter or temporary-table mechanism.
- A run reads what it started with. Anything the store registers anew while
  the run is part way through (a source's mapping today) is chosen once when
  the run first starts, kept in its frozen scope (`mdm.run.scope`), and read
  back on every later call and resume, never resolved again per batch. The
  commit still checks it.

## Choose the cheapest proof

Name the claim in one sentence, then take the smallest cohort that can falsify it. The agent chooses that cohort; the operator does not pick a size each time (operator, 2026-10-24: "the skill must be intelligent and use the most optimal path"). A proof drops work that cannot change the claim. A recurring load is a different claim and still processes every file ([data-operations](../data-operations/SKILL.md), "Size the work").

| The change | The proof |
|---|---|
| Any code, a migration, a rules or data file | The affected tests, locally, and CI (`AGENTS.md`, "Tests and CI") |
| A rule upstream of MDM (a source extract, a combine step) | Compare the changed step's output over a capture, and the combined output on one bundle. Equal combined bytes mean everything downstream is unchanged |
| The Merge Stage engine, a worker, Bookkeeping | A Proving Run on a pinned cohort, and the full installed proof on an empty store: every count as before, a killed worker resumes, the second pass changes nothing |
| Matching rules, a Dataset Contract | The smallest cohort that contains each new case. One slice whose second pass changes nothing proves the path on real records. A case that slice did not contain is the one bundle that contains it, then stop. The whole delivery is the proof only when the claim is that delivery's totals, or switch-on |
| A storage adapter or a change claimed to work across databases | The shared per-engine behavior checks above for every affected kind and source; preserve restricted-role, transaction and recovery guarantees |
| Speed | Time per batch over a whole feed: flat, not growing with the store. Each worker's process time is in the run's progress lines; `mdm.merge` gives one total for matching, survivorship, links and the save (`MergeStage.apply`), so a time per Merge Stage step needs a profile of one Proving Run's merge, or a timer per phase in its report. Measured (installed proof, 2026-10-12, 6,726 source documents): `source.read` 0.10 s a document, `mdm.prepare` 13 ms a document, `mdm.merge` 25 ms a record |
| A version whose rules moved since its last proof, each change proven by its own merged PR at the level this table names for it | No new run: carry the last proof forward. Write a proof file from the last one: its counts and `batch_hash`, `passed: true`, `digest` set to the new version's digest (`rules record-proof` refuses any other), its acquisition evidence if it had any, and under `evidence` and `note` the run it came from and each change since with its PR. Record it with `rules record-proof --proof-uri --proof-sha256`; `rules pending` then shows that evidence for approval. A change without such a proof gets its own row's proof first |

Say the time of any proof over ten minutes before starting it. When a run
shows a case the cohort did not contain, prove that case and stop. Name what
stays unchecked, including the delivery's totals until switch-on. A domain
skill that names a whole-delivery test uses that test only when the claim is
the delivery's totals or switch-on. So does a ticket's checklist: a line
written as "proof on the capture" is met by the limited test that answers its
claim, never by a multi-hour run that repeats it at scale (operator,
2026-10-28: "Why do we need to run a 5-hour proving run this is a waste").
Stop the proof's containers when it ends,
whatever the outcome.

### Independent installed qualification

Install the committed runtime and native libraries outside the checkout. Check
all package revisions and runtime import paths before and after each scenario.
Copy required test scaffolding and frozen non-code fixtures into a separate
harness directory, checking fixture hashes. Keep checkout runtime paths out of
the isolated caller's import path.

For a refusal or rollback claim, first accept an otherwise identical valid
request. Inject one fault, assert the specific refusal reason, and compare all
affected durable state. An arbitrary exception can hide an invalid test request.
Exercise destination commit checks as well as application validation.

Keep private diagnostics and per-case outcomes in a session-owned directory
outside automatically rotated test temporary roots. Record engine, configured
kind, case, revision, configuration pin, elapsed time and verified cleanup.
Publish counts and outcomes only. A family closes only when every required case
passes for each selected engine and configured kind on the final revision.
Exclude temporary-directory symlink aliases from artifact uploads; count each
expected engine/kind/case once and refuse missing or contradictory outcomes.

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
  whole-list search), `tests/storage_adapters/test_record_scope.py`
  (indexed scope and validated references),
  `tests/storage_adapters/test_prepared_effects.py` (indexed reads and a request
  beyond the former size cap), and `tests/mdm/test_clean_limits.py` (input
  batching keeps an oversized record).
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
- **Lean cohort** (operator, 2026-10-24): ticket 120. A slice of the
  Securities proof passed twice, and the CUSIP half of the quarter matched.
  The ISIN half's only new case was one CUSIP offered two ISINs that share a
  FIGI, inside the first bundle. The other seven bundles were the same join,
  about 11 hours: over-processing. Stop after the bundle that holds the new
  case. The quarter's totals stay unchecked until switch-on.
- **The full installed proof** for the Company population:
  `.planning/workstreams/whole-source-census/installed_proof.py` (its
  docstring has the command; about 28 minutes; 6,414 Companies, 3,052 GLEIF
  bindings).
