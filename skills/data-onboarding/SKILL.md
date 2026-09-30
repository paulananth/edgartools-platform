---
name: data-onboarding
description: Bring a NEW data feed or a NEW domain (for example Person) into Clean MDM and silver, starting from its captured files. Identify the feed, profile it, map its fields and identifiers, write its first data quality checks, generate its metadata (Mapping Document and Data Catalog entry), test it, get the operator's approval and switch it on. Also sets up the Rules Database (init, migrate). Use when the user wants to add or onboard a feed, a source or a domain that has no rules file yet. To change something already live, use refining-rules.
---

# Data Onboarding

Brings something **new** into Clean MDM (and silver): a feed with no rules
file yet, or a domain (a kind such as Person) with no merge rules yet.

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
| Approve with no test run | Run **test** first. A failing run may be overruled, a missing one never. |
| Request anything from `sec.gov`, including its documentation | Use the captured files and this repo |
| Read, print or paste a secret, password or token | Use the environment variables named here. If one is missing, ask the operator to set it outside the chat. |
| Guess an identifier (a CIK, an LEI, any key) | Take it from the files |
| Invent a command this skill does not name | Follow "When a command is missing" |
| Ask several questions at once | Ask one, in plain words, with your recommendation |

## What you produce

Everything lives in YAML files under `rules/` in this repo. People review
them in PRs. [REFERENCE.md](REFERENCE.md) is the contract language.

| File | What it holds |
|---|---|
| `rules/sources/<source>/source.yaml` | The feed: `source`, `bronze` and `mdm` (one Dataset Contract per source code). Its `bookkeeping` section, which runs the feed into silver and MDM, belongs to the Bookkeeping skill. |
| `rules/sources/<source>/quality.yaml` | The feed's data quality checks and fixes |
| `rules/merge/kinds/<kind>.yaml` | A new domain's matching and merge rules (only when the kind is new) |
| `rules/sources/<source>/MAPPING.xlsx`, `rules/merge/kinds/<kind>.xlsx` | The Mapping Documents, generated for stewards (**metadata**) |
| The Data Catalog (OpenMetadata) | Every feed, dataset and MDM field, published from the files (**metadata**) |

The worked examples are the files already in `rules/sources/`: `gleif`
(three files, native publications) and `sec.submissions.company` (one
reader, a silver target and an MDM target).

## Two targets: MDM and silver

Every step says what differs for each target.

- **MDM target.** The feed's records become MDM records through its
  Dataset Contract (`mdm` section) and its kind's merge rules. Everything in
  this skill builds it.
- **Silver target.** The feed's records land as typed rows. For a feed with
  a reader (SEC submissions), the silver step is a step of its
  `bookkeeping.targets` pipeline (`company.silver`). The Bookkeeping skill
  writes and runs that section.

  A general silver writer (Delta or Lakebase tables from `rules/outputs.yaml`)
  is **not built** (rules-skill ticket 05). For a new feed with no reader,
  say so, log it, and onboard the MDM target only.

## How to run commands

- From the repository root:
  `uv run --extra mdm edgar-warehouse rules <command> …`. The CLI takes
  about half a minute to start; that is not a hang.
- Never run `python -m edgar_warehouse.cli`. It prints nothing and exits 0,
  so a missing command looks like success.
- Read and write rules files only through `edgar_warehouse.rules.files`
  (`load`, `source`, `dumps`, `write_source`). It refuses YAML that would
  change a value silently (`yes`, `010`, a date).
- Environment:

  | Variable | Login | Used by |
  |---|---|---|
  | `RULES_DATABASE_URL` | `rules_agent` | every rules command |
  | `RULES_MIGRATION_DATABASE_URL` | owner | **init** and **migrate** |
  | `RULES_MDM_ACTIVATION_DATABASE_URL` | MDM governance | **switch-on** |
  | `OPENMETADATA_URL`, `OPENMETADATA_TOKEN` | — | catalog publish |

## The log

Keep `<your scratchpad>/onboarding-log.md`. Record:
- every question and its answer;
- every command this skill names that did not exist;
- every guess, and each test input you built by hand.

The operator reads it, and it is how this skill gets fixed.

## Modes, in order

A new feed runs **identify → profile → map → quality → metadata → test →
approve → switch-on**. Set up the Rules Database first if it is not there
(**init**).

### init: create the Rules Database schema

```bash
uv run --extra mdm edgar-warehouse rules init
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
uv run --extra mdm edgar-warehouse rules migrate
```

This is the same as **init**, run again after a new migration file lands.
Rerunning it changes nothing. It never moves rules files: that is
`rules load` (files to the database) and `rules unload` (database to files,
**without their comments**). Unload only into another folder and compare;
never unload over the repo's `rules/`.

### identify: name the feed, and find out whether it is new

1. Look at the files: their names, formats, sizes and first records. Name
   the provider and the dataset, e.g. "ACME company registry, monthly CSV
   extract". Ask: "These look like X. Is that right?"
2. Search `rules/sources/` and the repo for the provider's and dataset's
   names.
   - **Its rules file exists:** stop. This is **refining-rules**.
   - **The repo names it** (a source code, a reader, a rank in the merge
     rules) **but it has no rules file:** carry on here, and keep every name
     the repo uses.
3. Check registration:
   `uv run --extra mdm edgar-warehouse rules status --source <name>`. An
   empty list means it is not registered. If you cannot reach the Rules
   Database, ask.
4. **Names.** When the repo does not fix a name, derive it from the names
   it already has, and never invent a new pattern:
   - one folder per source, even when one reader reads several files (GLEIF
     is one folder, `gleif`, for three files);
   - one source code per file or record type, `<source>.<record type>.v1`
     (e.g. `gleif.level1.v1`, `gleif.relationships.v1`);
   - the capture family the repo already names for these files; if it names
     none, the folder name. Log it either way.
5. **A new domain.** If the records are a kind with no merge rules yet (no
   `rules/merge/kinds/<kind>.yaml`), say so. The kind must be in `KINDS`
   (`edgar_warehouse/mdm/clean/evidence.py`); a kind that is not there
   needs the operator's ruling. Check its written requirements, e.g.
   `docs/specs/person/consumer.md` for Person.

**Output:** a line in the log with the name, the source code(s), the family,
and whether it is a new domain.

### profile: learn the files' shape

`rules profile` is **not built yet**. Profile by hand, and log the gap:
1. Write a short script in your scratchpad that streams the files.
2. Profile a bounded sample first: records from the start, the middle and
   the end of each file (files are often sorted).
3. Make a full pass only for a count that decides something. Time the
   sample first, and say how long the full pass will take before you start
   it.
4. A file inside a zip is one compressed stream. Stream it with Python's
   `zipfile` (much faster than `unzip -p`). When a JSON pass is too slow,
   count with a line-based pass over the file's fixed layout, checked
   against the JSON pass on a slice.

For each record type, find:
- each path: its types, how often it is filled, its distinct count and
  samples;
- candidate record keys (unique and always filled);
- identifier-shaped values. An LEI is 20 characters and passes mod 97; a
  CIK is up to 10 digits. Say which you checked and how;
- repeated groups, and keys that point at other records (candidate
  relationships);
- names shaped like organisations or like people, dates and addresses;
- placeholder values for "none" (`000000000`, the text `NULL`, `8888`).
  Log each one.

A file may hold several record types: profile each separately. A table
stored as parallel arrays (one list per column) must be zipped into rows
first. When the reader accepts JSON and XML, check each list path in both:
XML often writes a list of one as a single object.

Count every defect (a failed check digit, a missing key, a malformed
record). A defect always blocks; do not ask whether it does. Log the counts
for a reader ticket.

**Output:** the profile in your scratchpad, and its summary in the log.

### map: write the Dataset Contract

**Research first.** If a document named here is missing, go on and log it.
- `CONTEXT.md`: the words MDM uses.
- `docs/specs/clean-mdm/`: start with `source-evidence.md` and
  `company-policy.md`.
- MDM kinds: `KINDS` in `edgar_warehouse/mdm/clean/evidence.py`.
- The fields MDM keeps for a kind. For Company, see the fields of the SEC
  contract (`FIELDS = CONTRACT["adapter"]["fields"]` in
  `edgar_warehouse/mdm/clean/company_source.py`) and the `company` table
  (`docs/specs/database-design-review-2026-09-30.md`). Use these names; a
  new field is a question for the operator.
- `rules/merge/kinds/<kind>.yaml`. It ranks sources per kind
  (`defaults.sources`: the first one listed wins each field), and its
  comments record which value fills a shared field. Read them before you
  ask about a shared field.
- **The reader.** Search for code that loads this source's rules file
  (`rules_files.source("<name>")`, `mdm_contract(`) or names its source
  code. If a reader exists:
  - map from *its* records, not the raw files;
  - do not write a second parser;
  - its names are fixed;
  - read its validation code, which may require exact values or refuse
    keys.
- The source's public documentation on the web, never `sec.gov`: field
  definitions, identifiers, how often it publishes, full files or changes
  only. Third-party pages are hints, not authority.

**Infer, for each record type:**
- **Kind:** from `KINDS`, or the field or rule that decides it.
- **Record key:** its parts, in the order the source defines its unique key
  (GLEIF: start, end, type). The order is part of each record's identity.
- **Identifiers:** each namespace and its format.
  - Ask about every identifier the source carries; never drop one silently.
  - Recommend keeping a cross-reference identifier as lookup-only, under its
    own name (operator, 2026-09-26).
  - Only `cik` and `lei` can join two records into one.
  - An identifier another authority issues is named for who stated it
    (`sec_lei`), never for the issuer.
- **Fields:** use the kind's names.
- **Relationships:** type, the other end's key, the source it lives in,
  start and end. List every type the source carries. Label each mapped one's
  `scope` `<Provider> <relationship family>`.
- **A value of another kind** (e.g. a ticker belongs to Security, not
  Company) stays out of this kind; log it for that kind.
- **Provenance:** trace stays beside the record (operator, 2026-09-27).
  Capture hashes, run ids and sync times never go into `provenance`. Only
  the source's own record may, when the reader keeps it (`native_record`).
- **A value the reader drops:** write a comment where it would go, and log a
  reader ticket. Never map a path the reader lacks.
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
- Write the values with `files.dumps`. Then add short YAML comments by hand,
  between keys, wherever a choice needs a reason: an operator's answer, a
  field left out, a surprising path.
- Check it: `files.source('<source>')` must equal what you passed to
  `files.dumps`.
- Write only `source`, `bronze` and `mdm`. Keep any `bookkeeping` section
  as it is.

**A new domain** also needs `rules/merge/kinds/<kind>.yaml`: its
`defaults.sources`, its identifiers (Identifier Contracts), and a first
matching rule on an issued identifier (e.g. `cik` for SEC filers). Copy the
shape of `rules/merge/kinds/company.yaml`. A matching rule on names is
never written here: it needs a measured proof, which is **refining-rules**
work.

**Silver target:** for a feed with a reader, the Bookkeeping skill writes
the `bookkeeping` section's steps. Hand it the feed's name and the target.

**Output:** `source.yaml` (and a new kind file, for a new domain) that loads
cleanly.

### quality: the first data quality checks and fixes

From the profile, list what would harm a match or a merge. Pick a check or
fix for each from REFERENCE.md, "Data quality":

| Problem | Check or fix |
|---|---|
| A code the source writes wrongly, or for "none" (SEC's `DC` state, `000000000`) | A fix that blanks it (`blank_values@1`) |
| A registered agent's or placeholder address | A check that withholds it from matching (`on_fail: withhold`); it stays on the record |
| A critical data element missing (e.g. no name) | A check that makes the record an exception (`on_fail: exception`). It never merges and never stops the run. List its reason `quality_<id>` in the contract's `nonblocking_deferred_reasons`, or registration refuses the contract. Keep these few (operator, 2026-09-28). |
| Anything worth watching | A check that only counts (`on_fail: flag`) |

- Every check reads the record *after* the mapping (`fields.<name>` or
  `matching.<name>`), never the raw file.
- A check or fix not in REFERENCE.md is new code: log it for a ticket; do
  not write it.
- Count, on the profile sample, how many records each would touch. Ask the
  operator about each `on_fail` and each fix, with its count and two or
  three examples.
- Write `rules/sources/<source>/quality.yaml` (`version`, then `quality`,
  one entry per source code), never inside the contract.
  `files.write_source(body, folder)` writes both files.
- `files.source('<source>')` must load with `quality` inside each contract.

### metadata: the Mapping Document and the Data Catalog

1. Generate the Mapping Document:
   ```bash
   uv run --extra mdm edgar-warehouse rules mapdoc write --only <source>
   ```
   For a new kind, run it again with `--only <kind>`. It writes
   `MAPPING.xlsx`, and its Notes sheet starts with your comments.
2. Give the workbook to the stewards and the operator. Apply their changes
   through **refining-rules** ("change-mapping"), and repeat until they
   agree it. Only an agreed mapping goes on to **test**.
3. Check that it matches the rules:
   `uv run --extra mdm edgar-warehouse rules mapdoc check`. It must pass,
   and CI fails otherwise. Commit the workbook with the rules.
4. After the PR is merged, publish to the catalog:
   `uv run --extra mdm edgar-warehouse rules catalog publish`. It needs
   `OPENMETADATA_URL` and `OPENMETADATA_TOKEN`. Never print the token. If
   no catalog server is reachable, say so; do not skip it silently.

### test: run it on real captured files and record the result

1. **Dry run.** `rules check` and Preview are **not built yet**. Do this by
   hand and log it:
   - **Feed with a reader:** run the reader on 5–10 sample records in the
     source's own format. A reader of numbered releases (GLEIF) also needs
     publication details and an approved list of identifiers. Call its
     per-record function (`gleif_source.record_evidence`) with details taken
     from the file names, and label them as test inputs in the log.
   - **Feed with no reader:** pass records through
     `edgar_warehouse.mdm.clean.adapters.normalize`:
     - `contract=` your contract, `source_code=` your code,
       `policy=files.policy()`;
     - `publication={"artifact_sha256": <sha256 of the sample file>,
       "member": <file name>, "publication_key": "dry-run", "revision": 0}`.
   - Check the kind's merge rules accept the source. A source missing from
     `defaults.sources` fails its whole batch
     (`merge.check_company_sources(files.policy(), assertions)` for
     Company). Adding it is a merge-rule change: log it for the operator.
   - Run the reader's tests, if any:
     `uv run --no-sync pytest -q <those files>`.
   - `normalize` runs the quality checks. Each record shows what they did
     under `provenance.quality`, and an `exception` raises
     `UnsupportedRecord("quality_<id>")`. Report the counts
     (`edgar_warehouse.mdm.clean.quality.counts(records, deferred)`) and up
     to 10 examples of each.
2. **A proving run, for anything that matches records.** A Company-scale
   example is `.scratch/company-mastering/research/27_proving_run.py`: real
   captured files, a disposable PostgreSQL 16, the Merge Stage, and a
   second pass that must change nothing.
3. **Save and record the test run:**
   ```bash
   uv run --extra mdm edgar-warehouse rules save --source <name> --version <v> rules/sources/<source>/source.yaml
   uv run --extra mdm edgar-warehouse rules record-proof --source <name> --version <v> --proof-uri <uri> --proof-sha256 <sha256>
   ```
   The proof names:
   - the version's `digest`;
   - the input `batch_hash` (the captured files' manifest sha256);
   - whether it `passed`;
   - `evidence` (the counts and up to 10 examples);
   - a one-line `note`.

   A failing run is recorded too; it can be replaced until it is approved.
   For a new kind, save and prove the merge rules the same way, using
   `--merge <name>`.

### approve: the operator decides

Follow [APPROVE.md](APPROVE.md). Explain in plain words, ask once, and
record their exact words.

### switch-on: activate, then hand the run to Bookkeeping

Activate as in [APPROVE.md](APPROVE.md), "Switch on".

Running the feed is the **bookkeeping** skill's **run** mode, with
`--source <name> --feed <feed>`. It submits `rules run --target <target>`
with an input manifest and its sha256. Run the MDM target first, then
silver.

## When a command is missing

This skill names some commands before they are built. When you reach one:
- if the step says what to do instead, do that in your scratchpad;
- if it does not, stop at that step and tell the operator.

Either way, write it in the log.

| Command | State | What to do | Built by |
|---|---|---|---|
| `rules profile` | not built | Profile by hand (**profile**) | rules-skill ticket 06 |
| `rules check` | not built | Dry run by hand (**test**) | rules-skill ticket 03 |
| Preview (matches against a copy of MDM) | not built | A proving run on a disposable PostgreSQL 16 (**test**) | rules-skill ticket 04 |
| General silver writer | not built | Onboard the MDM target only (**Two targets**) | rules-skill ticket 05 |
