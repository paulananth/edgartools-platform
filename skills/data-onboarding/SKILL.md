---
name: data-onboarding
description: Bring a NEW data feed or a NEW domain (a kind with no merge rules yet) into MDM and silver, starting from its captured files. Profile the data set with the data-profiling skill, plan one onboarding per part, map its fields and identifiers, write its first data quality checks, generate its metadata (Mapping Document and Data Catalog entry), test it, get the operator's approval and switch it on. Also sets up the Rules Database (init, migrate). Use when the user wants to add or onboard a feed, a source or a domain that has no rules file yet. To change something already live, use refining-rules.
---

# Data Onboarding

Work lean: check each step against [the seven wastes](../data-platform/SKILL.md#the-seven-wastes) and drop what adds no value.

> Part of the **data-platform** skill, installed as one package with its
> commands. Start there for setup (install, stores, `edgar-warehouse doctor`)
> and for the whole flow; this skill holds one step's detail.

Brings something **new** into MDM (and silver): a feed with no rules
file yet, or a domain (a kind) with no merge rules yet.

**Use the other skill when:**
- the feed already has `rules/sources/<source>/source.yaml`, and you are
  changing its mapping, its data quality or the matching rules: use
  **refining-rules**;
- you are running a feed, or recovering a run: use **bookkeeping**;
- you are recording or recovering journal evidence: use **change-journal**.

## Hard stops

Read these before anything else. Breaking one is never the right call.

| Never | Instead |
|---|---|
| Approve for the operator, or record words they did not say | Ask, wait, record their exact words ([APPROVE.md](APPROVE.md)) |
| Switch on (activate) a version the operator has not told you to switch on | Ask, wait, record their exact words ([APPROVE.md](APPROVE.md)) |
| Approve with no test run | Run **test** first. A failing run may be overruled, a missing one never. |
| Ask the operator to approve a digest, hash or version number they cannot read | Say in plain words what the version does, what it changes and on what evidence, under its descriptive name; the digest goes beside it, never instead |
| Name a Rules version by a number alone | A label that says what it changes (the **test** step's version label, `<source or kind>-<YYYY-MM-DD>.<short change name>`) |
| Write a value from the data (a name, an identifier, a record) into a public repository | Counts, and invented examples; real values stay on the machine |
| Request anything from a provider the operator has ruled out, including its documentation (see Examples) | Use the captured files and this repo |
| Read, print or paste a secret, password or token | Use the environment variables named here. If one is missing, ask the operator to set it outside the chat. |
| Guess an identifier (any key or issued id) | Take it from the files |
| Edit code while onboarding, even for a code ticket the operator approved | Configuration only: write the ticket for the code, and ask before coding |
| Invent a command this skill does not name | Follow "When a command is missing" |
| Ask several questions at once | Ask one, in plain words, with your recommendation |

## Tell the discovery story as you work

**Coordination note for every LLM:** keep this section and data-profiling's
narration when editing either skill; change them only on the operator's
explicit instruction (operator, 2026-10-09: "more story telling ... i need to
know what it is finding no more ... discussion and slop").

Narrate as data-profiling's
[Tell the discovery story as you work](../data-profiling/SKILL.md#tell-the-discovery-story-as-you-work)
says, through every step of onboarding: each update is a finding with its
numbers and meaning, never a description of the step you are about to take.
Onboarding's findings are fields, identifiers, defects, refusals and test
results, and how each changes the proposed onboarding. Label each result for
what it proves: explored, approved, tested locally or active. A command that
succeeds proves only what it checks.

Not: "Next I'll reconcile the export with the workbook to confirm the counts."
Instead: "The export has 3,022 rows; the workbook reader refuses the original
file, so these counts are explored, not yet read by the contract."

At a question or approval pause, give the evidence and your recommendation,
then follow the approval gate. Record findings and open questions in the
onboarding log as well.

## What you produce

Everything lives in YAML files under `rules/` in this repo. People review
them in PRs. [REFERENCE.md](REFERENCE.md) is the contract language.

| File | What it holds |
|---|---|
| `rules/sources/<source>/source.yaml` | The feed: `source`, `bronze` and `mdm` (one Dataset Contract per source code). Its `bookkeeping` section, which runs the feed into silver and MDM, belongs to the Bookkeeping skill. |
| `rules/sources/<source>/quality.yaml` | The feed's data quality checks and fixes |
| `rules/sources/<source>/silver-<table>.yaml` | A silver table spec, one file per table (silver target): reviewed in the PR, registered from this file |
| `rules/merge/kinds/<kind>.yaml` | A new domain's matching and merge rules (only when the kind is new) |
| `rules/sources/<source>/MAPPING.xlsx`, `rules/merge/kinds/<kind>.xlsx` | The Mapping Documents, generated for stewards (**metadata**) |
| The Data Catalog (OpenMetadata) | Every feed, dataset and MDM field, published from the files (**metadata**) |

The files in `rules/sources/` show Dataset Contracts and publication rules.
For configured complete JSON source extract, find a feed that keeps each
document whole (`grep -l "format: json" rules/sources/*/source.yaml`, then
its `read:` block) and read [data-platform READING](../data-platform/READING.md). A declared target is
not evidence that its workers exist; check every profile before submitting.

## Two targets: MDM and silver

Every step says what differs for each target.

- **MDM target.** The feed's records become MDM records through its
  Dataset Contract (`mdm` section) and its kind's merge rules. Everything in
  this skill builds it.
- **Silver target.** A transaction or published reference part lands in a
  silver table made from its approved silver table spec (the part's `silver`
  in `findings.yaml`). The spec's links point to master parts only; fill each
  link's `kind` and `source_code` (the master's Dataset Contract) from the
  onboarded master, since the writer looks each row's MDM id up by them and
  refuses a link without them.
  - **One link, one Dataset Contract.** The writer finds a row's MDM id by
    the source key among the records that one Dataset Contract staged. When
    a key may have been staged by either of two contracts (one column holding
    either of two identifier types), give that column two links, each with its
    own MDM id column; each row fills the one whose contract staged its key.
  - **A master whose record key has several parts** is found by that key as
    MDM writes it: the parts as a compact JSON list (`["<part 1>","<part 2>"]`).
    Build that text as a column in the reading (`concat` of the parts) and
    test it against `adapters.record_key` on the master's contract.
  - **Keep the source's own shape for rows several parties share.** When one
    record names several parties for the same lines, land the lines once and
    the parties in their own table, joined by the record's key, as the source's
    own published data sets do; never repeat a line per party, or a sum over
    parties counts it several times.
  - **The spec goes in the repo.** Write the approved spec to
    `rules/sources/<source>/silver-<table>.yaml` (comments carry the rulings),
    put the same spec in the part's `silver` in `findings.yaml`, and
    regenerate `profile.yaml` (**plan-parts**), so the catalog shows the table
    that is registered.
  - **Its checks are in the spec.** The data-quality skill writes them into
    the spec's `checks`; a failing row lands flagged in its `quality` column.
  - **Prove the link.** A test lands invented rows beside the master's
    records, keyed apart from the identifier, and asserts each MDM id; a link
    pointed at another Dataset Contract must fail it.

  - **A link stated on each transaction row is a lookup, not an MDM record**
    (a fund's holding of a security, an order's supplier). Land the rows in
    silver with one link per master; the writer fills each MDM id by its key.
    Never stage one MDM record per row only to master the link (operator,
    2026-10-22: "Why do you need to merge it it's just a lookup").
  - **Never carry a many-to-many link as a list on a record.** A reduction keeps
    at most 1,000 members per list (`sample_limit`), so a widely held entity
    loses links silently: one row per link instead.
  - **The row's link key is the master's record key, as its contract makes
    it.** Repeat the contract's own choice (an identifier, else another, a
    folded key) in the rows' contract, and prove every row's key is a record
    key the master's contract makes from the same files.
  - **Rows for silver get their own reading**, beside the master's, so the
    master's reading and its pinned digests do not change.
  - **Limits on a production feed are the engine's ceilings** (operator,
    2026-10-22: "No limit on production", "I asked to remove all limits").
    The engine requires each to be declared, so "no limit" means its ceiling:
    a stream's `max_input_bytes`, `max_bytes` and `max_spool_bytes` 1 TiB,
    `max_records` and `max_output_rows` 10^12, `max_partitions` 10^7,
    `max_record` 32 MiB, `partition_bytes` 8 MiB, `partition_records`
    100,000; a lookup set's `max_values` 100,000,000, `max_bytes` 16 GiB,
    `max_value_bytes` 16,384; a combine's `max_rows` 40,000,000; a reading
    over pieces `execution.max_input_bytes` and `limits.max_bytes` 16 GiB,
    `limits.max_records` 100,000,000. A streamed reading's `read.limits`
    bounds one row: at most 32 MiB and 100,000.
  - **Check it on the largest real case before any run** (operator,
    2026-10-22: "make sure the logic is correct and works for a major fund
    issuer"): cut that case's files out of the capture, run the real
    contracts on them in pieces as a run cuts them (8 MiB, 100,000 rows; a
    large combined output arrives as a version-2 index of pieces), and count
    every row by outcome.
  1. Hand the approved spec to
  [data-operations](../data-operations/SKILL.md), which applies it as DDL.
  On PostgreSQL the schema owner (`SILVER_MIGRATION_DATABASE_URL`) runs
  `edgar-warehouse silver init --runtime-role <runtime login>` once, and
  `edgar-warehouse silver register rules/sources/<source>/silver-<table>.yaml --runtime-role <runtime login>`
  for the table (or `register <findings.yaml> --part <part>`). A changed
  spec is refused for a registered table: register it as a new table.
  MySQL and SQL Server Express use the same spec. When `silver register`
  refuses that dialect, data-operations reports the gap and does not
  hand-write `CREATE TABLE`.
  2. The runtime (`SILVER_DATABASE_URL`, plus `MDM_DATABASE_URL` to read MDM
     ids) runs `edgar-warehouse silver land <table> <rows file>` with the
     part's rows as a flat CSV, Parquet or JSON Lines file. A rerun of the same
     delivery changes nothing; an unmastered record keeps its source key and an
     empty MDM id. Once its master is onboarded, `edgar-warehouse silver
     refresh-ids <table>` fills the ids of rows already landed.
  3. `edgar-warehouse context silver <table>` shows an agent what the table holds.

  Scheduled landing through the declared pipeline still needs a verified
  output worker (`edgar-warehouse workers describe <profile>`); Bookkeeping
  owns orchestration. A missing profile is unfinished implementation: record
  the gap.

## How to run commands

- `edgar-warehouse rules <command> …`. `edgar-warehouse` is the installed data skill bundle (see the **data-platform** skill, Setup). In a checkout of the repository, put `uv run --extra mdm --extra s3` in front of it instead. Run `edgar-warehouse doctor`
  first. The CLI takes from half a minute to three minutes to start; that is not a hang.
- Run the `edgar-warehouse` command, never the `edgar_warehouse.cli` module
  through Python. The module prints nothing and exits 0,
  so a missing command looks like success.
- Read rules files only through `edgar_warehouse.rules.files` (`load`,
  `source`), which refuses YAML that would change a value silently (`yes`,
  `010`, a date). Write a new file with `files.dumps` or
  `files.write_source`. Change an existing file as text instead, since those
  functions drop its comments, which hold decisions. Either way, check it
  with `edgar-warehouse rules check --source <source>`.
- **Where you write.** On your own branch, write straight into the repo's
  `rules/`; the PR is the review. To draft without touching the repo (a
  trial, a sandbox), copy `rules/` to a folder and pass that folder:
  - to Python: `root=<folder>` in `files.source`, `files.mdm_contract` and
    `files.policy`;
  - to commands: `--root <folder>` in `rules check`, `rules mapdoc` and
    `rules catalog`.
  In a sandbox or trial, keep the log beside that folder, not in the repo.
- Environment:

  | Variable | Login | Used by |
  |---|---|---|
  | `RULES_DATABASE_URL` | `rules_agent` | every rules command |
  | `RULES_MIGRATION_DATABASE_URL` | owner | **init** and **migrate** |
  | `RULES_MDM_ACTIVATION_DATABASE_URL` | MDM governance | **switch-on** |
  | `OPENMETADATA_URL`, `OPENMETADATA_TOKEN` | — | catalog publish |

  A command that stops with `KeyError: 'RULES_DATABASE_URL'` means the
  variable is not set. Ask the operator to set it outside the chat. Never
  paste it.

  No Rules Database is live yet (operator, 2026-10-06: "There is no login").
  Until one is, do not ask for these variables: record each approval on the
  ticket with the operator's exact words and the ET time, and note that the
  database record waits. The walk then needs only Docker (or a local
  PostgreSQL 16) for **test**.

## The log

Keep `.scratch/onboarding/<source>/onboarding-log.md` on your branch. The
operator reads it later, so never put it in a temporary folder. Record:
- every question and its answer;
- every command this skill names that did not exist;
- every guess, and each test input you built by hand.

The operator reads it, and it is how this skill gets fixed.

## Modes, in order

A new data set runs **discover → plan-parts**, then each part runs
**identify → profile → map → quality → metadata → test → approve →
switch-on**. Set up the Rules Database first if it is not there (**init**).

**Run each long step once per part** (operator, 2026-10-15: "Data onboarding
should not run this many times"). One master part took about ten runs: five
profiling runs, three test runs and two Proving Runs. Each repeat came
from a fault found mid-run, or from a re-check that proved nothing new.
- Profiling, the test run and the Proving Run each run once per part.
- Before a long run, check what can stop it partway: the reader accepts the
  format; no size bound, cap or limit is below the data's measured size
  (profiling gives it); the profiler or engine has no open fix pending.
  Fix those first.
- Run a step again only when its input files, its rules or the engine
  changed and that change has no proof of its own; otherwise carry the last
  proof forward ([mdm-engineering](../mdm-engineering/SKILL.md#choose-the-cheapest-proof),
  "Choose the cheapest proof"). Re-run only that step, never the steps
  before it.
- Never re-run a step to confirm a result. The first run's report is the
  evidence.
- A Proving Run is not repeated after approval when the approved rules
  differ from the proved copy only in their approval fields.
- Questions the findings do not answer go to that part's one test or Proving
  Run. Never run another scan of the data for them.

### discover: profile the whole data set first

**Know the source first** (operator, 2026-10-15). Before the one profiling
run, read once what is already known about the source, and write it in the
onboarding log under "The source":
- the repo: `rules/identifiers/` (each identifier type: shape, check digit,
  stand-ins), `docs/specs/`, `rules/reference/published/`, existing
  contracts and their comments, and earlier onboarding logs for the same
  provider;
- the provider's own documentation for the data set (field definitions, its
  identifiers, stand-in values such as all-zero ids, how often it publishes,
  full files or changes only), only with the operator's permission for that
  request (Hard stops);
- what MDM already holds: `edgar-warehouse context <kind> --search "<words>"`.

Then pass what it gives to the run: the existing kinds (`--kinds`), and each
known stand-in and identifier type, named in the log, so a finding that
matches it is expected and not news. Whatever the source's documentation
leaves open, the one profiling run measures. This is the same reading the
**map** step's "Research first" asks for, done once here; map reuses the log.

Before running profiling, inventory the captured formats against its supported
inputs. When an input is unsupported, record the actual reader refusal. Keep
that format gap separate from any exploratory export: a profile of an export
does not qualify reading the original capture or the installed worker path.

An investigative export must retain the raw capture hash, the exporter and its
version/hash, explicit sheet or region selections, original row coordinates,
and output hashes. Reconcile rows and cell values, preserving identifier text,
leading zeros, types, blanks, and every excluded header or metadata region in
the audit. Record unmeasured regions and unknown meanings in the onboarding
log. Bring findings to the operator before choosing keys, kinds or bindings;
leave production format support open until it has its own qualification.

Use the [data-profiling](../data-profiling/SKILL.md) skill on every file or
table of the data set, unless approved findings for these same copies already
exist (`approval.status: approved` in its `findings.yaml`, and the same input
files). Profile each source once, into its own folder, and reuse its findings
while its inputs and the profiler are unchanged (data-profiling, "Profile
once"). It says what each part is (master, reference, relationship,
transaction or metadata), its record key, its links, code lists, hierarchies,
time roles and personal columns, with evidence. Its questions and its
approval are the operator's, one at a time. Do not go on without approved
findings.

**Output:** the path of the approved `findings.yaml`, in the log.

### plan-parts: one onboarding per part, in dependency order

From the approved findings, list one onboarding per part, in this order
(operator, 2026-10-15: "first do mdm"):
1. master parts (MDM), each with the relationships marked `onboard: together`;
2. reference parts: the findings' `code_sets` become RDM code sets, needed
   where a value's meaning comes from a code (a master keeps its values as
   filed until then);
3. transaction parts and the relationships marked `separate` (silver target).

Metadata parts go to Bookkeeping, not here. Show the list to the operator,
then take the first part through **identify**.

Write the approved findings' public summary into the repo, so the Data
Catalog shows every part's silver fields, its data quality rules and the code
sets (names and counts only, never a value from the data):

```bash
uv run --with duckdb --with pyyaml python <data-profiling>/scripts/profile_data.py catalog \
  --findings <folder>/findings.yaml --out rules/sources/<source>/profile.yaml
```

`edgar-warehouse rules catalog plan` then shows them in its `silver` and `rdm`
databases.

**Output:** the ordered list of parts, in the log; `profile.yaml`.

### init: create the Rules Database schema

```bash
edgar-warehouse rules init
```

- **Needs:** `RULES_MIGRATION_DATABASE_URL`, the owner's login.
- **Before you run it:** the PostgreSQL 16 database `rules`, the login
  `rules_agent` and the role `rules_approver` must already exist. It does
  not create them. If they are missing, ask the operator.
- **Worked:** it prints each migration file with its checksum.
- **Fails:** the roles are missing, or it is not PostgreSQL 16. Ask the
  operator.

### migrate: upgrade the Rules Database schema

```bash
edgar-warehouse rules migrate
```

This is the same as **init**, run again after a new migration file lands.
Rerunning it changes nothing. It never moves rules files: that is
`rules load` (files to the database) and `rules unload` (database to files,
**without their comments**). Unload only into another folder and compare;
never unload over the repo's `rules/`.

### identify: name the feed, and find out whether it is new

1. Look at the files: their names, formats, sizes and first records. Name
   the provider and the dataset (a provider, what the files hold, how often
   and in what format). Ask: "These look like X. Is that right?"
2. Search `rules/sources/` and the repo for the provider's and dataset's
   names. Leave out `.scratch/**/trials/`: those are earlier trials, not
   the repo's decisions.
   - **Its rules file exists, and you are changing what it already maps:**
     stop. This is **refining-rules**.
   - **Its files already feed one kind, and you are adding another kind from
     them:** this is onboarding. It gets its own folder and source code (see
     "Names").
   - **The repo names it** (a source code, a reader, a rank in the merge
     rules) **but it has no rules file:** carry on here, and keep every name
     the repo uses.
3. Check registration:
   `edgar-warehouse rules status --source <name>`.
   - An empty list `[]` means it is not registered.
   - `KeyError: 'RULES_DATABASE_URL'` means no database is configured. Log
     it and go on; registration is only needed at **test**.
   - An error saying `rules.rule_version` does not exist means the Rules
     Database needs **init**.
4. **Names.** When the repo does not fix a name, derive it from the names
   it already has, and never invent a new pattern:
   - one folder per source, even when one reader reads several files;
   - one source code per file or record type, `<source>.<record type>.v1`;
   - a second kind from the same files gets its own folder named for the
     kind, the way the first one is, and its code is `<folder>.v1`;
   - the capture family the repo already names for these files; if it names
     none, the folder name. Log it either way.
5. **A new domain.** If the records are a kind with no merge rules yet (no
   `rules/merge/kinds/<kind>.yaml`), say so. The kind must be in `KINDS`
   (`edgar_warehouse/mdm/clean/evidence.py`); a kind that is not there
   needs the operator's ruling. Its written requirements (its spec under
   `docs/specs/`) are the requirements.

**Output:** a line in the log with the name, the source code(s), the family,
and whether it is a new domain.

### profile: read the part's findings

The approved `findings.yaml` (from **discover**) is the profile. For this
part, take:
- `record_key`: the key, and whether it was found or designed (a designed
  key carries its rule and the operator's answer);
- `identifiers`: the cross-reference proposals and check-digit families;
- `columns`: types, fill, distinct counts, masked samples, `sensitivity`;
- `code_lists`, `time` and the part's `relationships`;
- `quality`: defects found while profiling, for **quality**.

Ask only what profiling cannot know: which MDM field each column fills,
which source wins a field, and the `on_fail` of each check. A defect always
blocks; do not ask whether it does.

**Output:** the part's findings path and its summary, in the log.

### map: write the Dataset Contract

**Research first.** Start from "The source" in the log (**discover**, "Know the
source first"); read here only what it left out. If a document named here is
missing, go on and log it.
- `CONTEXT.md`: the words MDM uses.
- What MDM and RDM already hold: `edgar-warehouse context <kind|relationship|code set> <key|--search words>`
  (read only, at most 8 KB; [REFERENCE.md](REFERENCE.md), "Reading MDM's context").
  Check a kind's existing records, a relationship type's links, or a code set's
  codes before you map onto them.
- `docs/specs/mdm/`: start with `source-evidence.md` and the policy
  spec of the kind you map onto.
- MDM kinds: `KINDS` in `edgar_warehouse/mdm/clean/evidence.py`.
- The fields MDM keeps for a kind: `edgar-warehouse context <kind> --search`
  shows a live record's fields; the kind's field list in code, or, for a kind
  with none, its consumer spec's projection. Use these names; a new field is
  a question for the operator.
- `rules/merge/kinds/<kind>.yaml`. It ranks sources per kind
  (`defaults.sources`: the first one listed wins each field), and its
  comments record which value fills a shared field. Read them before you
  ask about a shared field. A new source of a kind that has others: rank
  them all with data-profiling's `rank_sources.py` ("Rank several sources")
  and propose the place it measures, not the end of the list by default.
- **Configured source extract.** Inspect the source's `read:` block and
  [READING.md](../data-platform/READING.md). Define the records passed to its
  Dataset Contract explicitly. For complete JSON evidence, `value: {path: .}`
  preserves the object in a named column; `mdm.prepare` selects that column
  with `record_column`. For projected rows, map from the configured columns.
  Retained source readers are comparison oracles during retirement: compare
  types, rows, refusals, assertion identities and provenance against them.
  What is still unfinished for each live source is in its ticket, not here;
  a raw projection does not qualify a full pipeline.
- The source's public documentation on the web: field definitions,
  identifiers, how often it publishes, full files or changes only.
  Third-party pages are hints, not authority. When the provider is ruled out
  (Examples), use the repo instead: the existing contract and its comments,
  `docs/specs/`, the published code sets in `rules/reference/published/` and
  the parsers.

**Infer, for each record type:**
- **Kind:** from `KINDS`, or the field or rule that decides it.
- **Record key:** its parts, in the order the source defines its unique key.
  The order is part of each record's identity.
  - **No publication time in a record key.** A delivery's date belongs in its
    publication, not the key, or each delivery makes a new record of the same
    entity (operator, 2026-10-22: "Fix 5"). A feed that restates its records
    in every delivery gives each delivery its own `publication_key` and a
    rising `revision` (its period, for example YYYYMM) in `mdm.prepare`, with
    `effective_at` its period end; a restatement left at revision 1 is
    refused ("contradictory publications").
  - A one-part record key is the plain value, not a one-item list: a test
    computes its subject from the value itself.
- **Identifiers:** each namespace and its format.
  - Ask about every identifier the source carries; never drop one silently.
  - An identifier with no format yet is declared, not coded: write
    `rules/identifiers/<name>.yaml` from its profiling finding
    ([REFERENCE.md](REFERENCE.md), "Identifier types").
  - Recommend keeping a cross-reference identifier as lookup-only, under its
    own name (operator, 2026-09-26): map it under `cross_references`
    ([REFERENCE.md](REFERENCE.md)).
  - Only an identifier a binding rule matches on joins two records into one;
    a name joins only through a proven name rule (operator, 2026-10-08:
    "Proven name rules may bind"), and a name id stays lookup only. Adding a
    joining identifier is a merge-rule change for the operator.
  - An identifier another authority issues is named for who stated it
    (`<stating source>_<id>`), never for the issuer.
  - A flag, role or type the source states about a record is evidence for a
    rule, never a key and never a decider on its own: such fields are often
    wrong or partial for the very records that matter.
- **Fields:** use the kind's names. A list-shaped field has no contract
  syntax yet: leave it out, say so, and log a ticket.
  - **A date that usually changes stays out of MDM** unless it adds meaning
    to the entity or switches it on or off (operator, 2026-10-22: "date that
    changes usually should not be in MDM unless it adds meaning to the entity
    or turn on or off"). A source's record-keeping dates (last updated, next
    renewal) change the master's version without changing the entity: keep
    them in silver, or as the record's own effective time. A creation date, or
    a status change with its date, stays.
  - **Evidence about a link stays on the silver row**, not on the master: the
    issuer's identifier a holding names is the holding's, while the held
    entity reaches its issuer by the link (operator, 2026-10-22: "Fix 1").
- **Relationships:** type, the other end's key, the source it lives in,
  start and end. List every type the source carries. Label each mapped one's
  `scope` `<Provider> <relationship family>`.
  - **Only a link that describes the entities is an MDM relationship**: a
    parent, an issuer, a role, a fund's adviser, which change rarely. A
    position or an event (a holding, a transaction), restated in every report
    with its amount, is a silver row carrying the MDM ids of both ends and
    its as-of date, the date it holds at, beside the date it was reported (operator,
    2026-10-22: "Agreed Remove HOLDS from MDM's relationship types", "Don't
    we need a as of date for holdings").
    When a source states two report dates, tell them apart by their values
    before choosing: the as-of date falls just before the delivery, while a
    period end such as a fiscal year end often lies after it. Count the
    values that fall outside the delivery's window; they are why each row
    keeps its own date.
  - A relationship ends only on an end the source states. A record missing
    from a later file, or a source that falls silent, closes nothing.
  - Order and compare by the date the event happened, never the date it was
    reported: a late report is not a conflict.
  - A name can state a relationship ("A Series of <trust>", "<name> dba
    <name>", "Trustee", "ET AL"). Count each such wording in the files and
    bring it to the operator as a proposed link, in the same onboarding as
    the entities (relationships come with MDM). Until ruled, the name stays
    as written; never cut it into two entities by hand.
- **Evidence not captured:** when a rule needs evidence the capture does not
  hold yet, the record waits (set aside, with the reason) and the capture is
  a task. Never decide from the row alone.
- **A value of another kind** (an identifier of a different kind of entity)
  stays out of this kind; log it for that kind.
- **Provenance:** trace stays beside the record (operator, 2026-09-27).
  Capture hashes, run ids and sync times never go into `provenance`. Only
  the source's own record may, when the reader keeps it (`native_record`).
- **An unmapped source value:** first test whether configured `value`, paths,
  iteration or frozen references can preserve it. Map only evidence the
  tested source extract emits. If the grammar cannot express it, record a minimal
  failing example and follow data-platform Mode 6 for a reviewed custom step.
- **The publication:** `semantics` (full file or changes only),
  `completeness` and `effective_time`.

**Ask** the real decisions, one at a time, each with your recommendation:
- whether a record type, or a relationship type, is in scope;
- which of two fields is authoritative;
- a new MDM field or kind;
- each identifier;
- the source code's name, when the repo does not fix it.

Do not ask:
- what the repo's names already fix;
- whether a defect blocks (it does);
- which value fills a shared field, when the kind file already says.

**Write** `rules/sources/<source>/source.yaml`, following REFERENCE.md and
starting from its "Defaults".
- Write the values with `files.dumps`, or both files at once with
  `files.write_source(body, folder)`. In that body, each contract's quality
  block sits inside it as `mdm.<code>.contract.quality`, with its own
  `version`. `write_source` moves it into `quality.yaml`; without it, no
  `quality.yaml` is written. Then add short YAML comments by hand,
  between keys, wherever a choice needs a reason: an operator's answer, a
  field left out, a surprising path.
- Check it: `edgar-warehouse rules check --source <source>` loads it as
  `rules save` would, offline. Each file says `ok`, or `refused` with the
  error's kind; it checks that the file loads (the loader refuses a value
  YAML would guess), that each Bookkeeping target and the acquisition hold,
  and that the merge rules pass.
  Run it with no `--source` after a change to the merge rules.
- Write `source`, `bronze`, `execution`, `read` and `mdm` for a configured
  captured-file path. The source worker requires
  `execution: {profile: source.read, workers: 1, max_artifacts: 1}`; workers
  may be 1 or 2 and max_artifacts 1 to 512 (one reading reads many documents:
  a unit per document wastes a worker start on each). Declare `read.limits.max_bytes` at
  most 33554432 and `read.limits.max_records` from 1 to 100000. Choose bounds
  from measured inputs and split oversized captures into explicit units;
  see [READING.md](../data-platform/READING.md) for output and preparation limits. The `acquisition` section (how
  the platform captures the files) and the `bookkeeping` section (how it
  runs them) belong to the Bookkeeping skill. Leave them out for a feed
  onboarded from files already captured, and keep them as they are in an
  existing file.

**A new domain** also needs `rules/merge/kinds/<kind>.yaml`. Copy the shape
of an existing kind's file, and declare:
- `defaults.sources`: your source code;
- **a classification rule**, if the files hold more than one kind under one
  source type. The contract names it under `adapter.classification` (`kind`,
  `rule_id`, `version`). A rule written for another source cannot be
  reused as it is: the engine refuses a rule whose `source` differs, so
  port it under a new id, and its proof must be measured again on this
  source. A step whose verdict is another kind becomes `verdict: deferred`
  with `probable_kind: <that kind>`; otherwise it blocks the batch;
- **a matching rule on an issued identifier**, shaped like an existing
  kind's, with its Identifier Contract. Leave out
  `verification`: it is filled in when the operator approves the contract
  on its proving corpus;
- `bars`, from the kind's written requirements;
- `defaults.allow_unknown_effective: true` if records carry no effective
  date. If they carry one, map it as `effective_at` in the contract
  ([REFERENCE.md](REFERENCE.md)); a contract that names its effective time
  in plain words but maps no `effective_at` gives its records only the
  publication's time, often none.

Never add the new rules to `automatic_rules` in `rules/merge/policy.yaml`;
that happens only at **approve**. A matching rule on names is never written
here: it needs a measured proof, which is **refining-rules** work.

**Execution target:** use the data-platform Parse and Master flow to declare
`source.read` → `mdm.prepare` → `mdm.merge` and any required publication
steps. Hand Bookkeeping the feed, target and verified worker profiles.

**Output:** `source.yaml` (and a new kind file, for a new domain) that loads
cleanly.

### quality: the first data quality checks and fixes

Use the [data-quality](../data-quality/SKILL.md) skill on this part, with
its approved findings and the field each column fills (from **map**):
**plan** (its `quality` items become the engine's checks; anything else is
new code, for a ticket), **measure** (on the records **test** builds),
**decide** (each `on_fail` and each fix with the operator, one at a time),
**mark** (invalid hierarchy rows, with evidence-backed fixes, for the
steward) and **write** (`rules/sources/<source>/quality.yaml`, never inside
the contract). Each `exception` check's reason `quality_<id>` goes in the
contract's `nonblocking_deferred_reasons`.

**Output:** `quality.yaml` that `rules check --source <source>` passes (it
loads `quality` into each contract), and the data-quality skill's `QUALITY.md`.

### metadata: the Mapping Document and the Data Catalog

1. Generate the Mapping Document:
   ```bash
   edgar-warehouse rules mapdoc write --only <source>
   ```
   For a new kind, run it again with `--only <kind>`. It writes
   `MAPPING.xlsx`, and its Notes sheet starts with your comments.
2. Give the workbook to the stewards and the operator. Apply their changes
   through **refining-rules** ("change-mapping"), and repeat until they
   agree it. Only an agreed mapping goes on to **test**.
3. Check that it matches the rules:
   `edgar-warehouse rules mapdoc check`. It succeeds
   silently, with exit 0. A difference fails it, and CI too. Commit the
   workbook with the rules.
4. Before the PR, see what would be published:
   `edgar-warehouse rules catalog plan`. This runs
   offline.
5. After the PR is merged, publish to the catalog:
   `edgar-warehouse rules catalog publish`. It needs
   `OPENMETADATA_URL` and `OPENMETADATA_TOKEN`. Never print the token. If
   no catalog server is reachable, say so; do not skip it silently.

### test: run it on real captured files and record the result

1. **Captured-file qualification.** Use 5–10 receipt-verified records first,
   with source hashes and publication facts taken from the capture. Execute
   the candidate `read:` contract with the configured engine and select
   precisely the records that `mdm.prepare` will send (whole rows, or its
   explicit `record_column`). Follow data-platform Parse and Master for the
   worker flow. Local tests may use a disposable candidate pipeline and
   approval fixture; label these as test-only, not an active Rules version.
   - Compare reading against retained readers when replacing them: values,
     types, order, refusals, counts and complete evidence. Preserve full
     publication checks and bounded streaming for numbered archive releases.
   - For a diagnostic normalization pass, use
     `edgar_warehouse.mdm.clean.adapters.normalize` with `contract=`,
     `source_code=`, `policy=files.policy(root=<draft folder>)` and captured
     publication facts. This tests mapping and quality only; it does not
     prove installed parsing, leases, receipts or MDM commits.
   - **A test over invented files** runs the configured rules through
     `tests/support/source_chain.py` (`read`, `combine`, `prepare`, each
     checked by its worker's verifier, then `records`). The test keeps only
     what is its own: the files, each artifact's context and lookups, and the
     preparation keys. Never copy the chain into a test.
   - Check the kind's merge rules accept the source. A source missing from
     `defaults.sources` fails its whole batch. Check `defaults.sources` (a
     kind with its own check in code, run it; see Examples). Adding a source to an
     existing kind is a merge-rule change: log it for the operator.
   - **A merge-rule change moves pinned digests.** Other tests pin a kind's
     policy digest, so run the whole MDM test folder (see Examples), not
     only the tests that load the rules. A kind whose digests are pinned
     layer by layer gets the change as one new layer: peeled, the policy
     is the one before. A new kind's own rules leave another kind's pins
     alone (a kind's pins cover its own part of the policy); a change to the shared
     part (relationship types, reference pins) moves them, and moves the
     integration answer file's whole-policy digest too.
   - **A new kind:** records are blocked with `classification_not_activated`
     until its classification rule is switched on. That is expected: the
     order below switches it on first. To see what it would do, add the
     verdict to a copy of the policy in memory only, and label that pass as
     a test input.
   - Run affected configured-engine and retained equivalence tests:
     `uv run --no-sync pytest -q <those files>`. Prove the full installed
     parse → prepare → merge path only when the change needs it
     ([mdm-engineering](../mdm-engineering/SKILL.md), "Choose the cheapest
     proof"). Record assertions, identities, quality counts and deferrals,
     not only row totals.
   - `normalize` runs the quality checks. Each record shows what they did
     under `provenance.quality`, and an `exception` raises
     `UnsupportedRecord("quality_<id>")`. Report the counts
     (`edgar_warehouse.mdm.clean.quality.counts(records, deferred)`) and up
     to 10 examples of each.
   - Report the run report checks too: per source, records and those set
     aside, the empty-value rate per field and the newest record's age
     (`quality.run_checks([quality.profile(records, deferred)], as_of=...)`;
     a Merge Stage run keeps them as `checks` in its report, `mdm.run.report`).
     They never block.
2. **A proving run, for anything that matches records, and only once.** A
   source whose last proof can be carried forward runs none. Which proof a change needs, and when the full installed proof is
   required, is in [mdm-engineering](../mdm-engineering/SKILL.md), "Choose
   the cheapest proof". For a new domain,
   nothing is switched on yet. So the run registers a **copy** of the
   policy, with the new rules added to `automatic_rules` and each stamped
   `approved_by: proving-run` and `reason: "Proving Run only; not an
   approval"`, in the disposable database only. The body the operator later
   approves differs only in those fields (an earlier proving run does
   exactly this; see Examples).

   **A source that declares a target** (`mastering`, unless `--target`
   names another, such as one target per kind of identifier asked) in a
   Bookkeeping section of version 2 (each step's `units` and `input`, in its `source.yaml`; see
   [bookkeeping SPEC](../bookkeeping/SPEC.md)) runs it with `rules test`
   instead of a pytest file. The input manifest is written from that
   declaration, so the reading may be one table or several. That runs the target twice on
   the disposable local stores, each step as its own login, and writes a
   counts-only report:
   ```bash
   uv run --extra mdm python infra/scripts/local-test-stores.py up <store name>
   edgar-warehouse rules test --source <name> --capture <capture folder> \
     --documents <list of document keys> --capture-run <run> --as-of <time> \
     --stores ~/.local/share/edgartools/local-tests/environments/<store name> \
     --out <report.json> [--target <target>] \
     [--fact <name>=<value> ...] [--file <name>=<path> ...]
   uv run --extra mdm python infra/scripts/local-test-stores.py stop <store name>
   ```
   A target that declares `run` takes each fact and file it names, and only
   those (a count, an approved scope; [bookkeeping SPEC](../bookkeeping/SPEC.md)).
   It refuses a store that already holds MDM records: `local-test-stores.py
   copy <new name>` gives a fresh one from the baseline. Invented documents
   need the kind's own shape: a document that carries another kind's
   structural fields (the ones the classification rule tests) is rightly
   held back, so an invented capture proves nothing about the kind. A
   version-1 section is refused: declare each step's units and input first.
   The writer forms units for a read of captured documents (slices, groups
   or each file, with per-document context, a companion file and same-file
   lookups), a read of a combine's pieces, `source.combine`, `mdm.prepare`,
   `mdm.merge` and `journal.record`, and a reading or lookup of another
   source's finished runs, `{run: {source, target, step}}`, which run first
   ([bookkeeping SPEC](../bookkeeping/SPEC.md));
   a target with any other step is refused. The same
   manifest for a real run comes from `edgar-warehouse mdm prepare-capture
   --source <name> --target <target>`, with the same `--fact` and `--file`.

   Otherwise, write it as a pytest file that uses the MDM fixtures, and it gets
   its own disposable PostgreSQL 16:
   ```python
   from tests.integration import test_clean_mdm_postgres as core  # its helpers
   # `postgres` starts one postgres:16 container for the session and removes it
   # after; `database` is a migrated MDM database of its own for each test.
   from tests.integration.conftest import database, postgres  # noqa: F401
   ```
   Run it with Docker (check `docker info` answers first), and bound it:
   `timeout -s KILL 600 uv run --no-sync pytest -q -s <file>`.
   `timeout` is GNU's; macOS has none, so there give the run a watcher with
   a deadline instead.
   Where Docker does not start, the same fixtures run on a local
   PostgreSQL 16 that is deleted afterwards:
   `PG16_SERVER=pgserver uv run --no-sync --with pgserver pytest -q -s <file>`
   (`tests/support/pg16.py`). Write in the log which one ran.
   - **Load every source that can bind the same entities.** A rule that
     creates entities is proved with every other source whose records can
     match the same entities (by an identifier or by name) loaded too;
     without them a duplicate cannot appear, and the run proves nothing
     about duplicates.
   - **Measure a known risk before the ruling.** When a ruling carries a
     risk (duplicate entities, links that cannot resolve), count it from
     the captured files first and give the operator the count, not only
     the sentence.
   - **Count the links MDM accepts, not the links a contract writes.** A
     test run shows each record's links; only the Merge Stage shows they
     resolve. Apply a few invented records through the whole chain and the
     Merge Stage first: a link with no stated start, from a publication
     that states no effective time, goes to review.
   - **Configuration first.** Before proposing an engine change, find what
     the rules files already allow (a rule's `on_no_match`, a reading's
     `context`, a reduction's keys or `last`) and put that option to the
     operator, with what it cannot do.
   - **Expect:** under a minute to start the database. A few hundred
     records should finish in under 5 minutes; several thousand take tens
     of minutes. Say the estimate before a long run.
   - **If it hangs or is killed,** its container stays up. List it with
     `docker ps --filter name=clean-mdm-test-` and remove it with
     `docker rm -f <name>`. Never touch any other container.
   A full run registers the datasets and policy, applies the bundles, and
   runs a second pass that must change nothing (Examples names one).
3. **The inputs and the proof.**
   - **Input manifest:** a JSON list of `{"member", "sha256", "bytes"}`, one
     entry per captured file, sorted by `member`. Its sha256 is the
     `batch_hash`. For a bronze capture with a `receipts.jsonl` (one line
     per file: key, sha256, bytes), use the sha256 of that file.
     The manifest lists exactly the files the test read: the feed's own, and
     a file another source captured when the reading joins it (a census,
     another feed's catalog), since the counts depend on it. A
     `receipts.jsonl` that names a file the test did not read, or misses one
     it did, is then not the manifest: write one with exactly those files.
   - **Digest, before saving:**
     `from edgar_warehouse.bookkeeping.clean.config import digest`. Then
     `digest(files.load_source(Path("rules/sources/<source>/source.yaml")))`
     for a source, or `digest(files.policy())` for the merge rules. It is
     what `rules save` will store.
   - **Proof file:** JSON with `digest`, `batch_hash`, `passed`, `evidence`
     and `note`. `--proof-uri` is `file://<absolute path>` locally or
     `s3://…`, and `--proof-sha256` is the file's sha256.
   - **Version label:** `<source or kind>-<YYYY-MM-DD>.<short change name>`,
     e.g. `acme.registry-2026-09-30.first`.
4. **Save and record the test run:**
   ```bash
   edgar-warehouse rules save --source <name> --version <v> rules/sources/<source>/source.yaml
   edgar-warehouse rules record-proof --source <name> --version <v> --proof-uri <uri> --proof-sha256 <sha256>
   ```
   The proof names:
   - the version's `digest`;
   - the input `batch_hash` (the captured files' manifest sha256);
   - whether it `passed`;
   - `evidence` (the counts and up to 10 examples);
   - a one-line `note`.

   A failing run is recorded too; it can be replaced until it is approved.

   **A source tested with `rules test`** records its run itself: save the
   version first, then add `--version <v>` to the `rules test` command, with
   `RULES_DATABASE_URL` naming the operator's Rules Database (set in their
   own terminal). The run is checked before it starts: the saved version must
   be the rules on disk. Its proof is the report's counts, and its
   `batch_hash` the first pass's input manifest. A source that declares
   `acquisition` records its test run the same way: the run switches on its
   pipes over files already captured. Its live acquisition is switched on
   apart, with a real acquisition run's evidence (`record-proof`).

   The merge rules are one document, `platform`, saved whole from
   `rules/merge/policy.yaml` (the kind files beside it come too):
   ```bash
   edgar-warehouse rules save --merge platform --version <v> rules/merge/policy.yaml
   edgar-warehouse rules record-proof --merge platform --version <v> --proof-uri <uri> --proof-sha256 <sha256>
   ```

**A new domain: the order of approvals.** Each step needs the one before it:
1. Measure the classification rule's proof on this source.
   - **The sample:** records drawn at random from the files, each labelled
     by hand against the kind's written definition (its spec's rule). Record who labelled them.
   - **The bar:** `bars.classification` (`min_precision`,
     `one_sided_confidence`). With every record correct, the Wilson lower
     bound is `n / (n + z²)`, so the least sample is
     `n ≥ p·z² / (1 − p)`. For example, 0.99 at 0.975 confidence
     (z = 1.96) needs 381; 0.95 at 0.95 (z = 1.645) needs 52.
   - **Record it** in `rules/merge/pending-proofs.yaml` under the rule's id,
     in the shape of the entries there: `method`, `one_sided_confidence`,
     `n`, `correct`, `lower_bound`, `adversarial` (`fixture_sha256`,
     `violations`), `cohort` (`files`: the sha256 of each input and
     script; `by_step`: a sample of its own per step of a rule with
     several), `approved_by: null`, `approved_at: null` and a one-line
     `reason`. Switch-on recomputes the bound from `n` and `correct`:
     write it cut to six places, never rounded up (the stated bound may
     not exceed the recomputed one, and must be within 0.00001 of it).
     The adversarial fixture holds pairs the rule must never join (a hard
     veto says they differ); `violations` counts those it joined, and
     must be 0.
2. The operator switches on the classification rule, then the identifier
   matching rule (APPROVE.md, "Switch one declared matching rule on").
3. Save, prove, approve and activate the merge rules (`--merge platform`).
4. Then test, approve and activate the source version. Its records now
   classify and match.

### approve: the operator decides

Follow [APPROVE.md](APPROVE.md). Explain in plain words, ask once, and
record their exact words.

### switch-on: activate, then hand the run to Bookkeeping

Activate as in [APPROVE.md](APPROVE.md), "Switch on".

Running it is the **bookkeeping** skill's **run** mode. It submits `rules run --target <target>`
with an input manifest and its sha256. Run targets in their declared
dependency order, and report any missing worker as unfinished implementation.

## When a command is missing

This skill names some commands before they are built. When you reach one:
- if the step says what to do instead, do that in your scratchpad;
- if it does not, stop at that step and tell the operator.

Either way, write it in the log.

| Command | State | What to do | Built by |
|---|---|---|---|
| Preview (matches against a copy of MDM) | not built | A proving run on a disposable PostgreSQL 16 (**test**) | rules-skill ticket 04 |
| Silver writer to a warehouse store | not built: the writer lands on PostgreSQL 16 only | Land on PostgreSQL 16 (**Two targets**) | a warehouse sink ticket (plan decision 36) |
| Flat export of a nested part | not built | Land flat parts; record each nested part as a gap | a follow-up of profiling ticket 06 |
| Silver output worker in a pipeline | not built | Run `silver land` by hand (**Two targets**) | a Bookkeeping worker ticket |

## Examples (this repo's sources)

These name today's sources only as examples; nothing above depends on them.

- **A provider ruled out:** SEC (`sec.gov`): never request it, nor its
  documentation. For an SEC feed, use the existing SEC contract and its
  comments, `docs/specs/`, and the published code sets.
- **Names:** GLEIF is one folder, `gleif`, for three files, with codes
  `gleif.level1.v1` and `gleif.relationships.v1`. SEC submissions feed
  Company (`sec.submissions.company`); Person from the same files is
  `sec.submissions.person` and `sec.submissions.person.v1`.
- **A record key's order:** GLEIF relationships: start, end, type.
- **Fields:** Company's are its contract reading's `fields` column
  (`rules/sources/sec.submissions.company/source.yaml`, and the Fields sheet
  of its `MAPPING.xlsx`); Person has none in code, so
  its consumer spec (`docs/specs/person/consumer.md`, "The Person
  projection") holds them. A list-shaped field: Person's `name_variants[]`.
- **Another kind's value:** a ticker belongs to Security, not Company.
- **Joining identifiers:** today `cik` (the one Identifier Contract); the SEC-to-GLEIF name rules
  (`sec-gleif-name-jurisdiction`, `sec-gleif-name-postal`) bind by name with
  their proofs.
- **Classification:** SEC types people and firms alike as `other`; the SEC
  Company contract names its rule under `adapter.classification`; a
  `company` verdict in a Person rule is deferred with `probable_kind`
  (`rules/merge/kinds/company.yaml`). `person-cik` on `cik` is shaped like
  `company-cik`. SEC submissions carry no effective date, so Company sets
  `allow_unknown_effective`.
- **Source checks in code:** for Company,
  `merge.check_company_sources(files.policy(), assertions)`.
- **Pinned digests:** `tests/mdm/` (757 tests, under a minute) holds them;
  Company's are layers in `tests/mdm/policy_layers.py` (`LAYERS`, newest
  first). N-PORT's registrant (2026-10-15) ran only the 43 tests that load
  the rules, and CI failed on four pinned digests.
- **Proving runs:** ticket 05's `.scratch/company-mastering/research/05_proving_run.py`
  (`candidate()` stamps the copied policy); ticket 27's
  `.scratch/company-mastering/research/27_proving_run.py` (6,726 records,
  about 25 minutes, a second pass that changes nothing).
- **Unfinished live pipelines** (the one list; other skills point here):
  `mdm.publish` delivers to a local contract sink only, not the required
  consumers' durable destinations; live acquisition (`provider.capture`,
  #933, qualified offline) waits for the worker runtime on AWS (ticket 71).
  A source's pipes switch on over captured files without it (#1108).
