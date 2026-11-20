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

The operator chooses PostgreSQL, MySQL or SQL Server Express. MDM has **one engine**: the mastering tables every merge
writes, and the rules it runs by, registered in the Rules Database. Entity and source names and field policies arrive as
data; storage holds no domain branch. Read [Storage on each database engine](references/storage-adapters.md) before
provisioning, initializing or reviewing storage. A silver table spec is applied by
[data-operations](../data-operations/SKILL.md).

- **One engine.** A store holds only the tables, code and commands its one engine uses; `init` installs only what a
  reader, command or stored record uses. A table, module or command nothing uses is removed in the change that stops
  using it: kept, it is loaded at every worker start, tested on every database and checked at every init.

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
runs by (the relationship types) is an RDM code set the policy
pins, each entry a code whose properties are its rules; one Rust module reads
the pinned rows and holds the one check, called at registration and before
every calculation. Python only carries rows to it and its error back. No code
copy, no default for a missing entry: a policy pinning none has no entries,
so what would use one goes to review.
A new capacity or type is a new published version (`rules/reference/published/<set>/<n>/`, the file's
sha256 in its `pin.json`) and a new pin in `rules/merge/reference-pins.yaml`; the committed workbooks
(`rules mapdoc write`) and the test fixture follow it. When a source field is not one of the
vocabulary's words, count how many rows state it first: where a few do, each refining a capacity
already held, the form's own word becomes a capacity with the stated text as its title.

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
- **Build the shared path once** ("Always build generic", `CLAUDE.md`). A second case of the same thing (an identifier class, a source, a format) reuses the first's path through a list or a parameter; never copy its table, rule or step. The cost of a copy is the next case's cost.
- **Remove a layer rather than tune it.** When a copy, a trigger chain or a
  table makes a step slow or hard to follow, prefer the design that deletes
  it over one that speeds it up. Adding an MDM field is data or policy, not a
  schema change spread across files.
- **No table scans.** Every read is by key, through an index, except a
  table that stays a handful of rows. A test shows it.

Before changing or defending a mastering step, read [MASTERING-STANDARD.md](MASTERING-STANDARD.md): the industry pipeline and
terms, matching order and outcomes, what a duplicate identifier means, the three separate decisions and what is code against
configuration.

## Cross-reference completion

**Retain computed matching evidence with its lookup keys.** A later source arrival must find both the key and
the evidence the matching rule reads on the stored holder. Write that evidence, keys, merges and waiting-record
release in one locked transaction. Prove a fault at release rolls them all back, then retry and repeat unchanged;
a committed key must never make a retry skip an unfinished release.

Read [CROSS-REFERENCE.md](CROSS-REFERENCE.md) before changing how identifiers are stored or looked up, qualifying native cross-reference lookup, or touching a rule that binds or consolidates by an identifier.

## The Merge Stage: each batch costs only what its records touch

**A batch replays at the time of its write.** A bundle's `as_of` is fixed when it starts, and bundles overlap, so a stored decision can carry a later time than the batch reading it. Replay sees every stored decision, and `as_of` is left to what a source states: a reading's effective date and field freshness. A replay that drops a stored bind writes that master with no members.

**Match first.** The batch's records are matched outside the save: each
identifier is looked up through its index; a record joins the master it
names, or a new master is proposed. Name rules follow, only where no
identifier exists. The save then checks the proposal again under the save
lock, and a proposal another run has overtaken is proposed again (a few
tries, then the run stops).

**A wrong consolidation is split by a steward, never edited**. `edgar-warehouse mdm steward split
--merge <decision id> --by <name> --reason <words> --policy-digest <digest>` previews, and `--confirm` writes one
`reverse` decision that names the merge, in one transaction with the replay of both masters' records. Both masters
return with their listings and links, and the reversed pair is a Match Exclusion (a later record reaching both goes
to review). A split merge is refused a second time; `context` shows a master's splits.

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

## A worker's memory is its imports plus its data

Every load runs several worker processes, and each pays for every library it imports before it reads a record. Import a
library that only some sources need (Parquet's pyarrow, with numpy under it) inside the function that uses it, never at
the top of a module a worker loads for every source. Measure before and after: `python -c` the modules a load imports and
read `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss`, and `footprint -p <pid>` on a running worker (macOS). A file a
run pins (`runtime_files`) is named without importing it, so the processing identity does not change. A worker's data
dominates a large load: bound what it holds (stream, never collect a whole file) before trimming a library.
`tests/unit/test_worker_imports_stay_small.py` holds the line.

Every load runs several worker processes. A worker holds a bounded piece of its input, never the whole of it: what must
span the input (the distinct keys of a receipt and a digest of them) goes to disk in sorted runs and is read back merged
(`silver_writer/keyset.py`), never held as a set of every key. Measure before and after with the same invented keys.

## Designing master fields
Before adding a field, column or table to the master store, or a reader of masters: [MASTER-FIELDS.md](MASTER-FIELDS.md).

## Lookups and indexes

On every engine, a list of keys is one index seek per key. A plan that scans
the table, or reads a whole index, is a defect. Several indexed columns are
separate seeks, never one `OR` across them. Reads are a few queries over the
batch's keys, never one query per record. A whole read is allowed only for a
table that stays a handful of rows, and its docstring says so. A test shows
the seek. Integer columns that count records are 64-bit (`BIGINT`). A read
selects only the columns it uses: a `LATERAL` subquery with `OFFSET 0` keeps
every column of its table, so selecting the whole table there carries a large
column into the plan; name the columns.

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

**A lookup over current masters is one table of tokens.** `mastering/lookups.py` builds `mastering_lookup` after a
load from the masters that changed: one row (token, master id) per name word, detail key and cross-reference, each
token the digest of what it finds under the pin of the configuration (`master_search` and `detail_lookups` in the
engine catalog). A changed configuration starts the build again from the first file, and a reader refuses until it is
built. A new lookup adds its tokens there, never a table or index of its own.

**A merge keeps an index only after the owner has built it.** An index with no
coverage row is not built, at any generation: the merge writes nothing for it
and readers refuse it. Load first, then run the owner rebuild once in bulk;
from then on each merge keeps it. Maintaining an index inside every batch of an
initial load writes most of a store's lookup entries for data that nothing reads
until the load ends.

**Page by keyset with two range reads, never an `OR`.** `a=%s and b>%s`, then `a>%s`, each ordered and limited, use the index; `a>%s or (a=%s and b>%s)` can scan. Standard SQL does both, so the portable form is the fast one. Time one page on the real store before a build runs over all of them.

**Ask for rows without a match with `not exists`, never `not in (select ...)`.** Over a subquery larger than the statement's memory, `not in` reads the whole subquery once for each row; `not exists` is one anti-join. Both are standard SQL. `not in` also answers nothing when the subquery holds a null.

**A store lookup is called before the loop or filter that uses its answer.** A call written inside a comprehension's condition runs once for every item, and each run is a round trip to the store. On a slow merge, sample the worker's session in `pg_stat_activity`: one statement in most samples, restarted each time, is this.

**Lock a table for the write, not while the worker prepares or sends rows.** Stage a delivery in a table of its own session first, then lock and merge; a lock or a lease held over the worker's own work makes a step run one unit at a time however many workers it has.

## Migrations

- `migrations/schema.sql` is the schema `mdm init` creates in an empty
  database. A schema change after go-live is a new numbered file beside it,
  added at the end of `store.MIGRATIONS`; never edit an applied file. A file
  left out of that list is never applied, and
  `tests/unit/test_every_mdm_migration_is_applied.py` fails for it.
- A registered name is an identity. A rule version keeps its steps, so a matching
  function's id cannot be renamed under it; a Dataset Contract keeps its
  `publication_key` words and `record_key`. Before renaming a word that is
  stored or registered, try the activation in the shared store (it refuses
  with "Rule version already registered" or "Dataset identity is immutable"),
  and keep the old word as the permanent name.
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
- A governed store keeps each batch's whole request, which can be a hundred
  MB or more after a large load. A read of records reads each
  batch's request once (the distinct batch keys), never once a record. A
  whole-store check still reads the current records (`iter_type`).

A module that moves between folders also breaks the paths it computes from its own
location: `Path(__file__).parents[N]` and `.parent`. Before the move, grep `parents\[`,
`__file__` and the files a runtime pin lists (`rules/`, `migrations/`), and run the whole CI set
(`tests/unit tests/architecture tests/mdm` plus `tests/engine`), not the tests of one folder.

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
  the run first starts, kept in its frozen scope, and read
  back on every later call and resume, never resolved again per batch. The
  commit still checks it.
- A store call that takes the lock does not commit. A step that must be all or nothing (a split, a reversal)
  is one function that takes the lock first, then does every write, then commits once, and rolls back on any
  error. Ordering separate calls cannot make it atomic.
- A merge takes the lock of its own kind only (`Store.take_lock(kind)`), so merges of two kinds run together.
  Of one kind, a merge runs beside the others under the kind's shared lock, and that includes creating a golden
  record for an identifier no one holds: the identifier values it newly gives are locked, one lock a value, then read
  again, so a merge that gives a value another golden record took meanwhile is sent to join it. A batch that holds more
  identifier values than one merge may claim beside others (the cap) is cut, before its first attempt, into parts that each hold
  at most the cap, in order, so the cut is a pure function of the records and a rerun finds each part's file done: each part
  is a file and a transaction of its own, and only a part that needs a merge alone holds the kind's lock, for its own short time,
  never the whole piece's. A kind lock
  serializes what a key lock allows: the batches of one source file carry disjoint keys. What only a merge alone may
  do (merge golden records, create by exact name, which no lock covers, or survive a deadlock) rolls it back, and it
  merges again holding the lock alone. Beside others it locks the golden records it rewrites (not one it created)
  before reading their members, and after its commit it looks once for a wait neither merge could see. MySQL merges one kind at a
  time. The locks are database locks (advisory and row), not tables. Its file stays in memory:
  a shared working table would force one lock for the whole store. Only a whole-store change (`clear`) takes
  the store's lock, with no kind.
- When a ruling changes what a load does (it joined, now it creates), re-check every lock rule that assumed the old
  behaviour, and time one batch alone, then the same batches beside each other, in a transaction rolled back, before
  the first full run. A load far slower than its batches alone is contention.
- Time a batch on the case the load is made of. A reload's records already have stored rows, and a path that only
  such records take (rewriting an older row) is missed by a batch of new records. When every session waits for the
  client and no worker uses CPU, look for one statement sent a row at a time.
- A changed golden record gets its file number when its transaction commits, never when it starts. A number
  given at the start lets a merge that commits late land below a reader's checkpoint, and the reader misses it.

## Choose the cheapest proof

Name the claim in one sentence, then take the smallest cohort that can falsify it. The agent chooses that cohort; the operator does not pick a size each time. A proof drops work that cannot change the claim. A recurring load is a different claim and still processes every file ([data-operations](../data-operations/SKILL.md), "Size the work").

| The change | The proof |
|---|---|
| A proof on a large delivery | [A sample chosen by kind](../data-profiling/SKILL.md#choose-a-proof-sample-by-kind): the batches richest in each rare case and one ordinary batch |
| A stage that changes what readers see, on top of its own proof | Trace one well-known entity end to end: every source that names it, its masters, its silver rows and links, and each reader's answer. Keep the questions as a script that runs again. A bulk comparison checks that two paths agree, and agreement hides what both get wrong; a traced entity shows a stripped identifier, an empty name or a missing link at once |
| A rebuilt merge path | Replay real stored records and compare with the stored masters: members, identifiers, each field's value, winner and conflicts. Pick whole masters, so none is cut in two, and run batches of the real size as well as one record a batch: each size hides faults the other shows. |
| Any code, a migration, a rules or data file | The affected tests, locally, and CI (`CLAUDE.md`, "Tests"). A source's rules file is also read by tests that never name the source, through a shared helper. Before the first push of a change to a source's rules, run the whole test folder CI runs for it once (`tests/integration` takes 12 minutes) rather than the files whose names match |
| A rule upstream of MDM (a source extract, a combine step) | Compare the changed step's output over a capture, and the combined output on one bundle. Equal combined bytes mean everything downstream is unchanged |
| A lookup moved to another read file | Compare the pair set from the old read and the new one on every captured delivery. Equal pairs prove every reader that uses the set: load one reader end to end at most, never each reader again |
| A source extract folded or split | Load the same capture with main and with the change on two disposable stores, then compare them (below) |
| The Merge Stage engine, a worker, Bookkeeping | A Proving Run on a pinned cohort, and the full installed proof on an empty store: every count as before, a killed worker resumes, the second pass changes nothing |
| Matching rules, a Dataset Contract | The smallest cohort that contains each new case. One slice whose second pass changes nothing proves the path on real records. A case that slice did not contain is the one bundle that contains it, then stop. The whole delivery is the proof only when the claim is that delivery's totals, or switch-on |
| A storage adapter or a change claimed to work across databases | The shared per-engine behavior checks above for every affected kind and source; preserve restricted-role, transaction and recovery guarantees |
| A new or deleted module the workers import | The installed-bundle tests (`tests/engine/test_data_skill_bundle_postgres.py`, the installed `tests/storage_adapters` files) after a commit: they build the bundle from the last commit, and the bundle ships only the modules `packages/data-skill/pyproject.toml` lists, so a module missing there passes every checkout test and fails every installed worker. Run the full local set after the last edit, not before it |
| Speed | Time per batch over a whole feed: flat, not growing with the store. Each worker's process time is in the run's progress lines; `mastering.merge` gives one total a file. |
| A version whose rules moved since its last proof, each change proven by its own merged PR at the level this table names for it | No new run: carry the last proof forward. Write a proof file from the last one: its counts and `batch_hash`, `passed: true`, `digest` set to the new version's digest (`rules record-proof` refuses any other), its acquisition evidence if it had any, and under `evidence` and `note` the run it came from and each change since with its PR. Record it with `rules record-proof --proof-uri --proof-sha256`; `rules pending` then shows that evidence for approval. A change without such a proof gets its own row's proof first |

**Compare two stores** by what they hold, never by the ids each store makes. Records: each body without its
assertion id and publication key. Silver rows: column by column, without the load time; an MDM id column by
how many rows hold one. Links: each master and assertion id mapped to the records it holds, and each evidence
list sorted, since it keeps store order. Build the links (`silver links`) after the kinds they point to are mastered. Two full loads side by side on one laptop share its memory, so
each runs slower than alone; say the pair's time.

Say the time of any proof over ten minutes before starting it. When a run
shows a case the cohort did not contain, prove that case and stop. Name what
stays unchecked, including the delivery's totals until switch-on. A domain
skill that names a whole-delivery test uses that test only when the claim is
the delivery's totals or switch-on. So does a ticket's checklist: a line
written as "proof on the capture" is met by the limited test that answers its
claim, never by a multi-hour run that repeats it at scale.
Stop the proof's containers when it ends,
whatever the outcome.

**A full-size proof runs once, with its final checks.** Before it:
review its checks (the Spec review included); run every step through the
installed commands on a sample (the answer key's few records) until it
passes; then run full size once. Each check states what it proves: the
source record found is not a value equal to it. A failed run keeps its
stores and restarts at the failed step; a rerun check (the second load
changes nothing) runs on a slice, not the whole load. A sample finds an
installed-bundle fault in minutes; a full proof run to find one is waste.

**A module reads a rules file through `rules.files.ROOT`**, never a path
beside a checkout (`Path(__file__).parents[n] / "rules"`): the installed
bundle ships `rules/` elsewhere, and the bundle test loads each such file
from the installed bundle.

### A record that carries only a name

- **The name rules (`name_binding`) serve one pair of sources only**: they need a Name Matching and a place test, so
  a Form ADV custodian named only by its name cannot use them. The rule for it is the `exact_name_binding`
  family (`edgar_warehouse/mdm/matching.py`): a source, its `holder_sources`, `key: name_id@1`, finds
  and never creates (`on_no_match: wait`, `on_several: review`).
- **Both sides must carry the name id as a cross-reference** (`name_id@1`, one fold for every source);
  a holder source that does not map it cannot be found. Adding it is a new contract version, not a new
  source code; a test's recorded answers are recorded again from the new contract.
- **A new candidate route changes the routes digest** that every stored record is indexed under
  (`matching_routes_sha256`); stored records must be reindexed, a rebuild store simply loads again.

### A lookup-only route, and the tests that pin rules

- **A retained source population includes history.** Use the shared current-record fold for revision and
  as-of selection, and compare its folded fields with the selected original's matching provenance.
  Keep that comparison view transient: save derived matching evidence on the original assertion,
  without replacing a patch's original fields with an accumulated snapshot. Test an omitted current
  field, a retraction, reversed row order and a future revision.
- **An installed-bundle test reads the committed rules.** `tests/engine/test_data_skill_bundle_postgres.py`
  installs from the commit's HEAD, so uncommitted rules give a stale answer (its policy digest was the
  old one). Commit first, then `uv sync --all-extras --group dev --reinstall-package edgartools-platform`,
  then run it.
  A shared namespace ships only the files its owning wheel lists: add a new runtime module to that wheel's
  inclusion table and prove its installed import; a checkout import cannot establish package completeness.
- **A policy or kind change moves the whole-policy digest** pinned in a test fixture
  (`tests/integration/fixtures/`, the mastering records file); the failing test prints the new value.
- **A single-valued identifier that fails its shape refuses the whole record**, its other identifiers too (a list
  of values sets only the bad value aside). Where a field is sometimes no identifier (a description
  written in a symbol field), the source rule empties it, so the record stays.
- **An Identifier Contract a binding rule uses needs a forward claim of at least 1** (the most
  records one value may reach before a review of its own; measure it, a reused symbol was at most 3),
  and the kind's source priority list names every source whose rule binds, even one that states no field.
- **A target prepares one publication**: a second dataset from the same files is a second target
  with a lighter reading of only the fields it needs.

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

**Count a store through its record reader, never its tables.** Governed
storage keeps the records in its own tables, so a count of the old `mdm`
tables reads an empty store whatever the run did. Count with `inspection.counts` and each
source record's current pointer, and grant the verifier what the installed
test grants. A proof whose counts are all zero proved nothing: treat it as
failed.

### Retire redundant tests by their obligations

Inventory collected cases for every selected engine, including fixture and
parameter variants. For each proposed retirement, answer five whys: the failure
it detects, its consequence, its current caller, the retained proof of the same
boundary, and what would be lost. Compare the complete setup and assertions;
similar names or overlapping happy paths do not establish equivalence. Keep
distinct authorization, migration, concurrency, rollback and recovery checks.

Map each retired case to executable retained proof, following replacements
through to a case that remains. Verify that proof rejects the relevant fault.
When removing a checkout wrapper, retain its shared scenario and the installed
engine/kind invocation. Record obsolete obligations separately from duplicates.
Count collected cases and existing fixture vectors separately; measure runtime
separately too. A percentage target is not evidence for removing a test.

Before deleting old code, find what is dead by the import graph from the live
entry points (the commands and worker operations), never by a runtime pin
list: a module named in a pin list looks reachable and is not. Delete the
modules with their pins and their tests in one change, port the tests whose
obligation still holds, and run the installed-bundle check that names required
modules, since it fails on a deleted name only in CI.

## Examples

- The Merge Stage is `edgar_warehouse/mastering/merge.py` and its store `edgar_warehouse/mastering/store.py`; what a
  batch reads is `edgar_warehouse/mdm/scope.py`; the input cut is `edgar_warehouse/mdm/limits.py` (1,000 records and
  1 MiB a batch); the migrations are registered in `edgar_warehouse/mdm/store.py` (`MIGRATIONS`).
- `tests/mdm/test_limits.py` holds the input batching rule (an oversized record is kept).
- Database portability runs the same pinned Company and Person fixtures and policies on every engine, plus every
  other affected kind and source. They are test cohorts, not limits on the shared merge algorithm.
