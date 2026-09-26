---
name: rules
description: Add a data source to Clean MDM, or change one, starting from its captured files. Identify the source, profile it, infer its MDM entities, identifiers, fields and relationships, ask the operator plain questions, write its rules file, then check, preview and run it after approval. Also initializes and migrates the Rules Database. Use when the user wants to add or onboard a source, change a source's mapping or the merge rules, or says "rules".
---

# Rules

Clean MDM's configuration lives in YAML files under `rules/` in this repo.
People edit the files and review them in PRs:

- `rules/sources/<source>/source.yaml`: one file per source. Its `mdm`
  section holds one Dataset Contract per source code: how the source's
  records become MDM records.
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
  silently (`yes`, `010`, a date).
- **A registered source code is live.** Change its mapping only with the
  operator, as a new version.
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
   (a source code, a parser, a rank in the merge rules), it is not new:
   - keep every name the repo already uses;
   - ask the operator whether its source code is registered in Clean MDM.
     `edgar-warehouse rules status` would say. *Not built yet:* ask;
   - follow "Change a source" below.

2. **Profile.** Run `edgar-warehouse rules profile <files>`. *Not built
   yet:* instead, write a short script in your scratchpad that streams the
   files. Log the gap. Profile a bounded sample first, for example the
   first 10,000 records of each file. Make a full pass only for a count that
   decides something, and time it on the sample before you start. For each
   record type, find:
   - each path, its types, how often it is filled, its distinct count and
     samples;
   - candidate record keys (unique and always filled);
   - values that look like identifiers. An LEI is 20 characters and passes
     mod 97. A CIK is up to 10 digits. Say which you checked and how;
   - repeated groups, and keys that point at other records (candidate
     relationships);
   - names shaped like organisations or like people, plus dates and
     addresses.

   A file may hold several record types: profile each one separately. It
   may also hold a table as parallel arrays, one list per column. Zip those
   into rows before you profile them.

3. **Research.**
   - **Terms:** `CONTEXT.md` defines the words MDM uses.
   - **Clean MDM:** read `docs/specs/clean-mdm/`, starting with
     `source-evidence.md` and `company-policy.md`.
   - **MDM kinds:** `KINDS` in `edgar_warehouse/mdm/clean/evidence.py`.
   - **Fields:** for Company, `COMPANY_NAMED_FIELDS` in
     `edgar_warehouse/mdm/clean/store.py` lists the fields MDM keeps; they
     are the Company table's columns.
   - **Ranks and matching rules:** `rules/merge/kinds/<kind>.yaml` says which
     source wins each field (`defaults.sources`) and how records match.
   - **Existing code for this source:** search the repo for the provider and
     dataset names. If code already turns these files into records (the
     source's *reader*), map from *its* records and name the command that
     runs it. Do not write a second parser. Find the reader by searching for
     the code that calls `normalize` for this source. When that code names
     the rules folder or a source code, those names are fixed.
   - **The source's public documentation on the web** (never `sec.gov`):
     field definitions, identifiers, how often it publishes, and whether
     each file is complete or holds changes only. When the source's own
     documentation is on a blocked site, rely on the files and the repo.
     Third-party pages are hints, not authority.

4. **Infer**, for each record type:
   - **Kind:** the kind from `KINDS`, or the field or rule that decides it. A
     new kind needs the operator's ruling.
   - **Record key:** the key and its format.
   - **Identifiers:** each namespace with its format.
   - **Fields:** use the names MDM already has for the kind. A new field is
     a question for the operator.
   - **Relationships:** the type, the other end's key, the source it lives
     in, and its start and end.
   - **The publication:** whether each file is complete or changes only
     (`semantics`), what a file covers (`completeness`), and when a record
     takes effect (`effective_time`).

5. **Ask.** One question at a time, in plain words, with your recommendation.
   The usual real decisions are:
   - whether a record type is in scope;
   - which of two fields holds the source's authoritative value;
   - whether a new MDM field or kind is wanted;
   - the source code's name.

6. **Write** `rules/sources/<source>/source.yaml`, in the shape of
   REFERENCE.md. Start from its "Defaults" section, and remember that a
   defect always blocks: a bad identifier or a malformed record is never a
   non-blocking reason. Write the values with `files.dumps`, then add a short YAML
   comment by hand wherever a choice needs a reason: an operator's answer, a
   field left out, a surprising path. Check that it still loads:
   `uv run --no-sync python -c "from edgar_warehouse.rules import files; print(files.source('<source>'))"`.

7. **Check.** Run `edgar-warehouse rules check <source>`. *Not built yet:*
   instead, run a dry run of the mapping on 5–10 sample records. When the
   source has a reader, run the reader on the sample: it reshapes records
   and applies checks that the mapping alone skips. Otherwise, put records
   in the reader's shape through `edgar_warehouse.mdm.clean.adapters.normalize`:
   - pass `contract=` your contract, `source_code=` your source code, and
     `policy=files.policy()`;
   - pass `publication={"artifact_sha256": <sha256 of the sample file>,
     "member": <file name>, "publication_key": "dry-run", "revision": 0}`;
   - show the operator what MDM would receive.

   Build the sample records with the source's parser, where one exists.
   Sometimes the parser needs inputs you do not have, such as another run or
   a census. Then build records in the parser's output shape by hand, from
   its code, and say so in the log.

   If the repo has tests for the parser you mapped from, run them:
   `uv run --no-sync pytest -q <those test files>`.

   This dry run is not a preview: it matches nothing against existing
   records. Log the gap.

8. **Preview.** Run `edgar-warehouse rules run <source> --target mdm
   --preview`, on a copy of the local MDM. *Not built yet:* stop here. Hand
   the operator the file, the dry run and the log.

9. **Approve, activate, run.**
   - The operator approves.
   - `rules activate` registers the source in Clean MDM.
   - `rules run <source> --target mdm --deploy`, then `--target silver`.

   *Not built yet.*

## Change a source or the merge rules

Follow steps 3 to 9. Show the operator what changes, record by record, from
the dry run before and after.

## Initialize or migrate the Rules Database

`edgar-warehouse rules init`, and `rules migrate --to-db` or `--to-files`.
*Not built yet:* tell the operator.

## When a command is missing

This skill is written before its commands. Each command is built when a trial
shows it is needed. When you reach a missing command:
- if the step says what to do instead, do that in your scratchpad;
- if it does not, stop at that step.

Either way, write it in the log.
