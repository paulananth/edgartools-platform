---
name: rules
description: Add a data source to Clean MDM, or change one, starting from its captured files. Identify the source, profile it, infer its MDM entities, identifiers, fields and relationships, ask the operator plain questions, write its rules file and its data quality checks and fixes, then check, preview and run it after approval. Also initializes and migrates the Rules Database. Use when the user wants to add or onboard a source, change a source's mapping, its data quality or the merge rules, or says "rules" or "data quality".
---

# Rules

Clean MDM's configuration lives in YAML files under `rules/` in this repo.
People edit the files and review them in PRs:

- `rules/sources/<source>/source.yaml`: one file per source. Its `mdm`
  section holds one Dataset Contract per source code: how the source's
  records become MDM records.
- `rules/sources/<source>/quality.yaml`: the source's data quality checks
  and fixes, run on each record before the merge. It has its own version
  name, and the loader puts it into each Dataset Contract as `quality`, so
  one approval covers the mapping and its checks.
- `rules/merge/policy.yaml` and `rules/merge/kinds/<kind>.yaml`: the merge
  rules (the Mastering Policy), one file per kind.

The files already in `rules/sources/` are worked examples. The contract
language is in [REFERENCE.md](REFERENCE.md).

## Hard rules

- **Captured files only.** Never fetch the source. Make zero requests to
  `sec.gov`, including its documentation pages.
- **Never approve.** Anything that feeds MDM needs the operator's approval.
  Ask for it and wait. Your recommendation is not a decision.
- **Never guess an identifier.** Take every CIK, LEI or other key from the
  files.
- **Read and write rules files only through `edgar_warehouse.rules.files`**
  (`load`, `source`, `dumps`). It refuses YAML that would change a value
  silently (`yes`, `010`, a date). The one exception: the comments you add
  by hand in step 7, checked by reloading the file.
- **Run commands with `uv`**, from the repository root:
  `uv run --extra mdm edgar-warehouse rules …`. The commands below leave the
  prefix out.
- **A registered source code is fixed.** Change its mapping only with the
  operator, as a new version. A change to what identifies a record (the
  contract's `record_key` or `publication_key`; the adapter's `record_key`,
  `record_key_format`, `identifiers` or `identifier_formats`) is refused
  within one source code: it needs a new source code (`….v2`).
- **When two written decisions disagree, the later operator decision wins.**
  Cite both in the log.
- **Ask about every identifier the source carries**; never drop one
  silently. The operator wants cross-reference identifiers kept for lookup
  (2026-09-26: SEC's EIN and SEC's stated LEI). Recommend keeping each one
  as a lookup-only identifier under its own name, and ask. Only `cik` and
  `lei` can ever join two records into one. An identifier a *different*
  authority issues (for example SEC stating an LEI) gets a name that says
  who stated it (`sec_lei`), never the issuer's name.
- **A value that belongs to another kind stays out of this kind.** Example:
  a ticker belongs to a Security, not a Company. Log it for that kind.
- **Read the source's documentation, never its data API.**
- **Questions:** plain words, one at a time, each with your recommendation.
  Ask only what the files, this repo and the source's public documentation
  cannot tell you.
- **Keep a log** at `<your scratchpad>/rules-log.md`. Record:
  - every question you asked, with the answer;
  - every command this skill names that did not exist;
  - every guess you made.

  The operator reads the log. It is how this skill gets fixed.

## Add a source

1. **Identify.** Look at the files: names, formats, sizes and the first
   records. Name the provider and the dataset, for example "ACME company
   registry, monthly CSV extract". Confirm with the operator: "These look like X. Is
   that right?" If you cannot tell, ask for the source's name.

   Then check whether it is new. Search `rules/sources/` and the repo for
   the provider's and dataset's names. If the repo already names this source
   (a source code, a reader, a rank in the merge rules), keep every name the
   repo already uses, and:
   - if its rules file exists, follow "Change a source" below;
   - if its rules file is missing, follow every step here (it needs a full
     profile), keeping the repo's names;
   - either way, find out whether its source code is registered: run
     `edgar-warehouse rules status --source <name>` (it needs
     `RULES_DATABASE_URL`). If you cannot reach the Rules Database, ask.

   **Names.** When the repo does not fix a name, derive it from the names it
   already has; never invent a new pattern:
   - one folder per source, even when one reader reads several files (GLEIF
     is one folder, `gleif`, for three files);
   - one source code per file or record type, in the pattern the merge rules
     already use: `<source>.<record type>.v1` (`gleif.level1.v1`, so its
     relationships file is `gleif.relationships.v1`);
   - the capture family: the family the repo already names for these files;
     if it names none, the source's folder name. Log it either way.

2. **Profile.** Run `edgar-warehouse rules profile <files>`. *Not built
   yet:* instead, write a short script in your scratchpad that streams the
   files. Log the gap. Profile a bounded sample first: records from the
   start, the middle and the end of each file, because a file is often
   sorted. Make a full pass only for a count that decides something, and
   time it on the sample first; when a JSON pass is too slow, count with a
   line-based pass over the file's fixed layout, checked against the JSON
   pass on a slice. A file inside a zip is one compressed stream: to reach
   its middle or end you must decompress everything before it. Stream it
   with Python's `zipfile` (much faster than `unzip -p`), time the first
   100 MB, and say how long the full pass will take before you start it.
   For each record type, find:
   - each path, its types, how often it is filled, its distinct count and
     samples;
   - candidate record keys (unique and always filled);
   - values that look like identifiers. An LEI is 20 characters and passes
     mod 97. A CIK is up to 10 digits. Say which you checked and how;
   - repeated groups, and keys that point at other records (candidate
     relationships);
   - names shaped like organisations or like people, plus dates and
     addresses;
   - placeholder values the source writes for "none" (`000000000`, the text
     `NULL`, a code such as `8888`). The contract cannot turn them into
     unknown yet: log each one.

   A file may hold several record types: profile each one separately. It
   may also hold a table as parallel arrays, one list per column. Zip those
   into rows before you profile them. When the reader accepts more than one
   format (JSON and XML), check each list path in both: XML often writes a
   list of one as a single object.

   Count every defect you find (a failed check digit, a missing key, a
   malformed record). Do not ask whether a defect blocks: it always does,
   even when the reader rejects it before it checks scope. Log the counts
   for a reader ticket.

3. **Research.** When a document named here is missing from your copy of
   the repo, go on without it and log it.
   - **Terms:** `CONTEXT.md` defines the words MDM uses.
   - **Clean MDM:** read `docs/specs/clean-mdm/`, starting with
     `source-evidence.md` and `company-policy.md`.
   - **MDM kinds:** `KINDS` in `edgar_warehouse/mdm/clean/evidence.py`.
   - **Fields:** for Company, `COMPANY_NAMED_FIELDS` in
     `edgar_warehouse/mdm/clean/store.py` lists the fields MDM keeps; they
     are the Company table's columns.
   - **Ranks and matching rules:** `rules/merge/kinds/<kind>.yaml` ranks the
     sources per kind, not per field (`defaults.sources`): a listed source
     may fill any field of the kind, and the first one listed wins. Its
     comments record which of a source's values fills a field that two
     sources share (the address, the name). Read them, and the comments in
     the other rules files, before you ask about a shared field.
   - **Existing code for this source (its *reader*):** search the repo for
     code that loads this source's rules file (`rules_files.source("<name>")`,
     `mdm_contract(`) or names its source code. If a reader exists, map from
     *its* records, not the raw files, and profile a few records in *its*
     shape too (build them from its code). Name the command that runs it.
     Do not write a second parser. Names the reader uses (the rules folder,
     source codes, versions, families) are fixed. Read its validation code:
     it may require exact values (a `schema_version`, a `family`, a
     publication family) or refuse keys.
   - **The source's public documentation on the web** (never `sec.gov`):
     field definitions, identifiers, how often it publishes, and whether
     each file is complete or holds changes only. When the source's own
     documentation is on a blocked site, rely on the files and the repo.
     Third-party pages are hints, not authority.

4. **Infer**, for each record type:
   - **Kind:** the kind from `KINDS`, or the field or rule that decides it. A
     new kind needs the operator's ruling.
   - **Record key:** the key and its format. Write its parts in the order
     the source defines its unique key (GLEIF: start, end, type). The order
     is part of each record's identity.
   - **Identifiers:** each namespace with its format.
   - **Fields:** use the names MDM already has for the kind. A new field is
     a question for the operator.
   - **Relationships:** the type, the other end's key, the source it lives
     in, and its start and end. List every relationship type the source
     carries; which are in scope is a question for the operator. Label each
     mapped relationship's `scope` `<Provider> <relationship family>`, for
     example `ACME ownership`.
   - **Kinds not settled:** when a category could be a kind the operator
     has not settled (for example Person before Person mastering), leave it
     unnamed and ask.
   - **Provenance:** trace stays beside the record, not in it (operator,
     2026-09-27). Capture hashes, run ids and sync times change with every
     capture, so they never go into `provenance`; the captured file's
     receipt names them beside the record. Map into `provenance` only the
     source's own record, when the reader keeps it under a key
     (`native_record`).
   - **A value the reader does not give yet:** when the operator wants a
     value the reader drops, write a comment where it would go and log a
     reader ticket. Do not map a path the reader lacks.
   - **The publication:** whether each file is complete or changes only
     (`semantics`), what a file covers (`completeness`), and when a record
     takes effect (`effective_time`).

5. **Quality.** From the profile, list what would harm a match or a merge,
   and pick a check or a fix for each from REFERENCE.md, "Data quality":
   - a code the source writes wrongly or for "none" (SEC's "DC" as a state
     of incorporation, `000000000`): a fix that blanks it
     (`blank_values@1`), so the field reads as unknown;
   - an address that is a registered agent's or a placeholder: a check that
     withholds it from matching (`withhold`); it stays on the record;
   - a value MDM cannot use at all (no name): a check that rejects the
     record (`reject`). A rejected record blocks its batch, as a defect does;
   - anything else worth watching: a check that only counts (`flag`).

   Every check and fix reads the record *after* the mapping (`fields.<name>`
   or `matching.<name>`), never the raw file. A test or fix that is not in
   the list is new code: log it for a ticket, do not write it. Count, on the
   profile sample, how many records each check and fix would touch; the
   operator decides with those counts (step 8).

6. **Ask.** One question at a time, in plain words, with your recommendation.
   The usual real decisions are:
   - whether a record type, or a relationship type, is in scope;
   - which of two fields holds the source's authoritative value;
   - whether a new MDM field or kind is wanted;
   - each identifier the source carries (see the hard rules);
   - the source code's name, when the repo does not already fix it;
   - each check's `on_fail` (reject, withhold or flag) and each fix, with
     its count from step 5 and two or three examples.

   Do not ask:
   - what the repo's names already fix (see "Names" in step 1);
   - whether a defect blocks (it does);
   - which value fills a shared field, when the kind file's comments or an
     existing rules file already say.

   Which reasons do not block is a decision: list only the ones the record
   decides (REFERENCE.md, "Blocking and non-blocking"), and ask about any
   other exclusion you expect.

7. **Write** `rules/sources/<source>/source.yaml`, in the shape of
   REFERENCE.md. Start from its "Defaults" section, and remember that a
   defect always blocks: a bad identifier or a malformed record is never a
   non-blocking reason. Write the values with `files.dumps`, then add a short YAML
   comment by hand wherever a choice needs a reason: an operator's answer, a
   field left out, a surprising path. `files.dumps` folds long values over
   several lines, so put comments between keys. Check that it still loads
   and that your comments changed no value: `files.source('<source>')` must
   equal what you passed to `files.dumps`.

   Write only `source`, `bronze` and `mdm`. The file's `bookkeeping` section
   (how its pipeline runs) belongs to the Bookkeeping skill; keep an
   existing one as it is.

   Write the checks and fixes to `rules/sources/<source>/quality.yaml`, never
   inside the contract (the loader refuses that): `version`, then `quality`
   with one entry per source code. `files.write_source(body, folder)` writes
   both files from one body. Then `files.source('<source>')` must load, with
   `quality` inside each contract you gave checks.

8. **Check.** Run `edgar-warehouse rules check <source>`. *Not built yet:*
   instead, run a dry run of the mapping on 5–10 sample records. When the
   source has a reader, run the reader on the sample: it reshapes records
   and applies checks that the mapping alone skips. Build small sample
   inputs in the shape the reader reads (a few records in a file of the
   source's own format) rather than running it on a whole large file.

   A reader of native publications (one that numbers and verifies each
   release, like GLEIF's) also needs the publication's details and an
   approved list of identifiers. Call its per-record function directly,
   with publication details taken from the file names and a scope made from
   the sample; label both as test inputs in the log.

   Then check the kind's merge rules accept the source: a source whose
   records are of a kind but which is missing from that kind's
   `defaults.sources` fails its whole batch
   (`merge.check_company_sources(files.policy(), assertions)` for Company).
   Adding it is a merge-rule change: log it for the operator; do not make
   it.

   A source with no reader: put records in the reader's shape through
   `edgar_warehouse.mdm.clean.adapters.normalize`:
   - pass `contract=` your contract, `source_code=` your source code, and
     `policy=files.policy()`;
   - pass `publication={"artifact_sha256": <sha256 of the sample file>,
     "member": <file name>, "publication_key": "dry-run", "revision": 0}`;
   - show the operator what MDM would receive.

   That `normalize` call skips what a reader adds (its publication key,
   record locators, deferred records). For a reader that builds batches,
   copy the loop in `edgar_warehouse.mdm.clean.cli.batch_input` into your
   scratchpad instead; it needs a database only for `current_reading`.

   Build the sample records with the source's parser, where one exists.
   Sometimes the parser needs inputs you do not have, such as another run or
   a census. Then build records in the parser's output shape by hand, from
   its code, and say so in the log.

   If the repo has tests for the parser you mapped from, run them:
   `uv run --no-sync pytest -q <those test files>`.

   `normalize` runs the contract's quality checks and fixes too. Each record
   it returns shows what they did under `provenance.quality` (the fixes with
   their original values, the withheld paths, the flags); a rejected record
   raises `UnsupportedRecord("quality_<id>")`. Give the operator the counts
   per check and fix (`edgar_warehouse.mdm.clean.quality.counts(records,
   deferred)`) and up to 10 examples of each: that is the proof they approve
   a quality version on.

   This dry run is not a preview: it matches nothing against existing
   records. Log the gap.

9. **Preview.** A preview shows real matches against a copy of the local
   MDM. *Not built yet:* stop here. Hand the operator the file, the dry run
   and the log.

10. **Save, prove, approve, activate, run.** Each command selects what it
   acts on with `--source <name>`, or `--merge <name>` for merge rules:
   - `edgar-warehouse rules save --source <name> --version <v> <file>`
     saves the file as a draft;
   - `rules record-proof --source <name> --version <v> --proof-uri <uri>
     --proof-sha256 <sha256>` records the proof of a passing run;
   - the operator runs `rules approve --source <name> --version <v>
     --digest <digest>` with `RULES_DATABASE_URL` set to their own approver
     login; the database records that login as the approver. Before you ask, say in plain
     words what the digest is and what it changes. Never run it yourself;
   - `rules activate --source <name> --version <v>` registers the version
     in Clean MDM. It also needs `RULES_MDM_ACTIVATION_DATABASE_URL` (the
     MDM governance login) and `CHANGE_LEDGER_DATABASE_URL` (the registry);
   - the run itself is the Bookkeeping skill's work (`$bookkeeping` in
     Codex, `/bookkeeping` in Claude): its `plan`, `validate` and `deploy` with
     `--source <name> --feed <feed>`. It submits `rules run`, which takes
     `--target` and an input manifest with its sha256. Run the MDM target
     first, then silver.

   `rules status --source <name>` shows each version's state.

## Change a source or the merge rules

Follow steps 3 to 10. Show the operator what changes, record by record, from
the dry run before and after.

## Check or change a feed's data quality

When the operator asks about a live feed's data quality, or a run's quality
counts look wrong:

1. Read the source's `quality.yaml` and the counts of its last runs.
2. Run the dry run of step 8 on a pinned sample (the files of one capture,
   named by their sha256). Report the counts per check and fix, with up to
   10 examples each.
3. For a new check or fix, or a change to one, follow steps 5, 6 and 8,
   then give `quality.yaml` a new `version` name. The source's contract
   changes with it, so the change is a new source version, saved, proved,
   approved and activated as in step 10. A new version applies to new
   batches only; it never rewrites a batch MDM already took.

## Initialize or migrate the Rules Database

- `edgar-warehouse rules init` creates the Rules Database's table and grants
  its roles their rights; rerunning it changes nothing. It connects with
  `RULES_MIGRATION_DATABASE_URL`, the owner's login. It does not create the
  database or the roles: a PostgreSQL 16 database named `rules`, the agent's
  login (`rules_agent`) and the `rules_approver` role must exist first, and
  it refuses without them. If they are missing, ask.
- `edgar-warehouse rules migrate --to-db --root rules --version <v>` saves
  every rules file as a version. `--to-files` writes them back, without
  their comments, and the comments hold decisions. Export to another folder
  and compare; never export over the repo's `rules/`.

Every other command connects through `RULES_DATABASE_URL`: the agent's
login, except for `approve`, which the operator runs under their own.
The CLI takes about half a minute to start; that is not a hang.

## When a command is missing

This skill is written before its commands. Each command is built when a trial
shows it is needed. When you reach a missing command:
- if the step says what to do instead, do that in your scratchpad;
- if it does not, stop at that step.

Run a command as `uv run --extra mdm edgar-warehouse …`, never
`python -m edgar_warehouse.cli`: that form prints nothing and exits 0, so a
missing command looks like success.

Either way, write it in the log.
