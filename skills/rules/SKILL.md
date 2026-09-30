---
name: rules
description: Add a data source to Clean MDM, or change one, starting from its captured files. Identify the source, profile it, infer its MDM entities, identifiers, fields and relationships, ask the operator plain questions, write its rules file and its data quality checks and fixes, generate its Mapping Document (a spreadsheet stewards review and change), then check, preview and run it after approval. Also initializes and migrates the Rules Database. Use when the user wants to add or onboard a source, change a source's mapping, its data quality or the merge rules, apply a steward's change to a Mapping Document, or says "rules", "data quality" or "mapping document".
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
- `rules/sources/<source>/MAPPING.xlsx` and `rules/merge/kinds/<kind>.xlsx`:
  the Mapping Documents, spreadsheets generated from the files above for
  people to read and change. Every sheet but Notes is generated; Notes is
  the stewards' own and is kept when the workbook is regenerated. A
  steward's change becomes rules only through you (see "A steward changed a
  Mapping Document"), and CI fails when a workbook differs from its rules.
- The Data Catalog in OpenMetadata: every source, feed, dataset and MDM
  field, published one way from these files by
  `edgar-warehouse rules catalog publish`. Nobody edits rules in it.

The files already in `rules/sources/` are worked examples. The contract
language is in [REFERENCE.md](REFERENCE.md).

## Hard rules

- **Captured files only.** Never fetch the source. Make zero requests to
  `sec.gov`, including its documentation pages.
- **Approve only on the operator's words, and only on test evidence.**
  Anything that feeds MDM needs the operator's approval (or the steward's,
  for their own Mapping Document change). They approve by saying so; you
  record it with `rules approve` under their name and their exact words
  ("Approve" below). Your recommendation is not a decision, and you never
  record an approval they did not give. No test run, no approval: the
  operator may overrule a failing run, never a missing one (operator,
  2026-09-29).
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
- **Keep the Mapping Documents equal to the rules.** After any change to a
  rules file, run `edgar-warehouse rules mapdoc write` and commit the
  workbooks with the change; `rules mapdoc check` (and CI) fails otherwise.
  Once the change is merged, run `edgar-warehouse rules catalog publish` so
  the Data Catalog shows it (it needs `OPENMETADATA_URL` and
  `OPENMETADATA_TOKEN`; never print the token). If no catalog server is
  reachable, say so; do not skip it silently.
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
   - a critical data element missing (no name): a check that makes the
     record an exception (`exception`). It never merges and never stops the
     run; it waits, open, until someone fixes or ignores it. List its reason
     (`quality_<id>`) in the contract's `nonblocking_deferred_reasons`:
     registration refuses the contract otherwise. Keep critical data elements
     few (operator, 2026-09-28);
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
   - each check's `on_fail` (exception, withhold or flag) and each fix, with
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

   These files are your working draft; nothing is saved to the Rules
   Database yet. Generate the source's Mapping Document from them:
   `edgar-warehouse rules mapdoc write --only <source>`. Its Notes sheet
   starts with the reasons you wrote as comments. Give the workbook to the
   stewards and the operator (operator, 2026-09-28: the Mapping Document is
   generated first, then stewards change it). Apply their changes as in "A
   steward changed a Mapping Document", and repeat until they agree it.
   Only rules whose workbook they agreed go on to step 10.

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
   their original values, the withheld paths, the flags); a record that fails an `exception` check
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
     --proof-sha256 <sha256>` records a test run, passing or failing. The
     proof names the version's `digest`, the input `batch_hash` and whether
     it `passed`; put what the operator reads under `evidence` (the counts
     and up to 10 examples of step 8) and one line under `note`. A failing
     run may be replaced by a new one until it is approved;
   - the operator approves it on its evidence ("Approve" below). For a
     change a steward made in a Mapping Document, merge priorities
     included, that steward approves it the same way (operator,
     2026-09-28);
   - `rules activate --source <name> --version <v>` registers the version
     in Clean MDM. It also needs `RULES_MDM_ACTIVATION_DATABASE_URL` (the
     MDM governance login) and `CHANGE_LEDGER_DATABASE_URL` (the registry);
   - the run itself is the Bookkeeping skill's work (`$bookkeeping` in
     Codex, `/bookkeeping` in Claude): its `plan`, `validate` and `deploy` with
     `--source <name> --feed <feed>`. It submits `rules run`, which takes
     `--target` and an input manifest with its sha256. Run the MDM target
     first, then silver.

   `rules status --source <name>` shows each version's state.

## Approve

The operator (or a steward, for their own change) approves a whole source or
the merge rules by saying so. Nobody types a digest, a login or an address.

1. Run `edgar-warehouse rules pending`. It lists each version with a test run
   and no approval yet: whether the run passed, its evidence (counts and up
   to 10 examples), its note, and `changes`, what it changes from the active
   version, value by value.
2. Tell the operator, in plain words and business terms, for each one: what
   it is (its name, never a digest), what it changes, and what the test run
   showed. A version with no test run is not listed and cannot be approved:
   run it first (step 10).
3. Wait for their words. Record only an approval they gave for that version:
   `rules approve --source <name> --version <v> --evidence <evidence_hash>
   --by "<their name>" --words "<their exact words>"` (`--merge <name>` for
   merge rules), with the version and `evidence_hash` that `rules pending`
   showed; you pass these, the operator never types them. It refuses a test
   run recorded since you showed it: show the new one and ask again. The
   database keeps the name, the words, the time, the evidence it rests on
   and your login beside them.
4. A failing test run is approved only when they overrule it, with their
   reason: ask for it, then add `--overrule "<their reason>"`. Recommend
   against an overrule you think is wrong, once, and say why. A source whose
   files could not be read (its acquisition checks failed) is never
   overruled: the approval is refused.
5. Then activate (step 10) and tell them it is in effect.

**One merge rule.** A matching rule declared in `rules/merge/kinds/` with its
proof in `rules/merge/pending-proofs.yaml` is switched on by itself. Say in
plain words what it joins and what its proof measured (the sample, how many
were right, the adversarial pairs), then wait for their words, and run
`rules approve --merge platform --rule <rule_id> --by "<their name>" --words
"<their exact words>"`. It adds the rule to `merge/policy.yaml` with its proof
and their approval, keeping the file's comments, and refuses a rule with no
proof or one short of its kind's bar (a single rule is not overruled
here: log it for a ticket). The merge rules that carry it are a new
merge version: save it, record its test run, and record the same words on it
when `rules pending` shows it changes only that rule; then activate.

## Change a source or the merge rules

Follow steps 3 to 10. Show the operator what changes, record by record, from
the dry run before and after.

## A steward changed a Mapping Document

A steward changes a workbook's cells (not only Notes) and commits it in a
pull request:

1. Run `edgar-warehouse rules mapdoc diff --only <source or kind>`. It lists
   each changed cell: the sheet, the row, the column, what the rules say and
   what the workbook says. A spreadsheet does not show its changes in a pull
   request; paste this list into it.
2. Turn each change into the rules files, with the hard rules above: an
   identifier or record key change needs a new source code; a test or fix
   not in REFERENCE.md is new code (log it for a ticket); a new MDM field or
   kind needs the operator's ruling. A change you cannot make: say why in
   plain words, and leave the rules as they are. The usual ones:
   - a row added to "Critical data elements": a `present@1` check on that
     field with `on_fail: exception` in `quality.yaml`, its reason
     `quality_<id>` listed in the contract's `nonblocking_deferred_reasons`;
   - "Preferred sources" reordered: `defaults.sources` in the kind file;
   - one field's winner changed ("Who wins each field"): a rule for that
     field in the kind file, `fields.<name>.sources`, in the new order. It
     takes the kind's `defaults` and changes only what it says; every other
     field keeps the default. A source left out of that list is ignored for
     that field: its values never win or conflict, so say so. A source not
     in the kind's `defaults.sources` is adding a source to the kind: that
     needs the operator's ruling, not the steward's. Otherwise it is a
     merge rules change: show which records' winners move, and the steward
     who made it approves it.
3. Run the dry run (step 8) and show what the change does, with counts and
   up to 10 examples. A change to "Preferred sources" or "Matching rules"
   moves which source wins or which records join: show those records.
4. Run `rules mapdoc write --only <source or kind>`. The generated rows
   replace the steward's; the steward confirms they say what was meant.
   `rules mapdoc check` must then pass.
5. Save and prove as in step 10. The steward who made the change approves
   it ("Approve" below); you record their words, never your own.

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
login (`rules_agent`), `approve` included.
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
