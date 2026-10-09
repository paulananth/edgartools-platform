---
name: data-onboarding
description: Bring a NEW data feed or a NEW domain (a kind with no merge rules yet) into Clean MDM and silver, starting from its captured files. Profile the data set with the data-profiling skill, plan one onboarding per part, map its fields and identifiers, write its first data quality checks, generate its metadata (Mapping Document and Data Catalog entry), test it, get the operator's approval and switch it on. Also sets up the Rules Database (init, migrate). Use when the user wants to add or onboard a feed, a source or a domain that has no rules file yet. To change something already live, use refining-rules.
---

# Data Onboarding

> Part of the **data-platform** skill, installed as one package with its
> commands. Start there for setup (install, stores, `edgar-warehouse doctor`)
> and for the whole flow; this skill holds one step's detail.

Brings something **new** into Clean MDM (and silver): a feed with no rules
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
| Approve with no test run | Run **test** first. A failing run may be overruled, a missing one never. |
| Request anything from a provider the operator has ruled out, including its documentation (see Examples) | Use the captured files and this repo |
| Read, print or paste a secret, password or token | Use the environment variables named here. If one is missing, ask the operator to set it outside the chat. |
| Guess an identifier (any key or issued id) | Take it from the files |
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

The files in `rules/sources/` show Dataset Contracts and publication rules.
For configured complete JSON reading, use `sec.submissions.person` and
[data-platform READING](../data-platform/READING.md). A declared target is
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
  refuses a link without them. Then:
  1. The schema owner (`SILVER_MIGRATION_DATABASE_URL`) runs
     `edgar-warehouse silver init --runtime-role <runtime login>` once, and
     `edgar-warehouse silver register <findings.yaml> --part <part> --runtime-role <runtime login>`
     for the part. A changed spec is refused for a registered table: register
     it as a new table.
  2. The runtime (`SILVER_DATABASE_URL`, plus `MDM_DATABASE_URL` to read MDM
     ids) runs `edgar-warehouse silver land <table> <rows file>` with the
     part's rows as a flat CSV, Parquet or JSON Lines file. A rerun of the same
     delivery changes nothing; an unmastered record keeps its source key and an
     empty MDM id until a later landing fills it.
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
  functions drop its comments, which hold decisions. Either way, reload it
  with `files.source` to check it.
- **Where you write.** On your own branch, write straight into the repo's
  `rules/`; the PR is the review. To draft without touching the repo (a
  trial, a sandbox), copy `rules/` to a folder and pass that folder:
  - to Python: `root=<folder>` in `files.source`, `files.mdm_contract` and
    `files.policy`;
  - to commands: `--root <folder>` in `rules mapdoc` and `rules catalog`.
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

### discover: profile the whole data set first

Use the [data-profiling](../data-profiling/SKILL.md) skill on every file or
table of the data set, unless approved findings for these same copies already
exist (`approval.status: approved` in its `findings.yaml`, and the same input
files). It says what each part is (master, reference, relationship,
transaction or metadata), its record key, its links, code lists, hierarchies,
time roles and personal columns, with evidence. Its questions and its
approval are the operator's, one at a time. Do not go on without approved
findings.

**Output:** the path of the approved `findings.yaml`, in the log.

### plan-parts: one onboarding per part, in dependency order

From the approved findings, list one onboarding per part, in this order:
1. reference parts (code sets for RDM; until RDM is built, log them);
2. master parts, each with the relationships marked `onboard: together`;
3. transaction parts and the relationships marked `separate` (silver target).

Metadata parts go to Bookkeeping, not here. Show the list to the operator,
then take the first part through **identify**.

**Output:** the ordered list of parts, in the log.

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

**Research first.** If a document named here is missing, go on and log it.
- `CONTEXT.md`: the words MDM uses.
- What MDM and RDM already hold: `edgar-warehouse context <kind|relationship|code set> <key|--search words>`
  (read only, at most 8 KB; [REFERENCE.md](REFERENCE.md), "Reading MDM's context").
  Check a kind's existing records, a relationship type's links, or a code set's
  codes before you map onto them.
- `docs/specs/clean-mdm/`: start with `source-evidence.md` and the policy
  spec of the kind you map onto.
- MDM kinds: `KINDS` in `edgar_warehouse/mdm/clean/evidence.py`.
- The fields MDM keeps for a kind: `edgar-warehouse context <kind> --search`
  shows a live record's fields; the kind's field list in code, or, for a kind
  with none, its consumer spec's projection. Use these names; a new field is
  a question for the operator.
- `rules/merge/kinds/<kind>.yaml`. It ranks sources per kind
  (`defaults.sources`: the first one listed wins each field), and its
  comments record which value fills a shared field. Read them before you
  ask about a shared field.
- **Configured reading.** Inspect the source's `read:` block and
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
- **Identifiers:** each namespace and its format.
  - Ask about every identifier the source carries; never drop one silently.
  - Recommend keeping a cross-reference identifier as lookup-only, under its
    own name (operator, 2026-09-26): map it under `cross_references`
    ([REFERENCE.md](REFERENCE.md)).
  - Only an identifier a binding rule matches on joins two records into one;
    a name joins only through a proven name rule (operator, 2026-10-08:
    "Proven name rules may bind"), and a name id stays lookup only. Adding a
    joining identifier is a merge-rule change for the operator.
  - An identifier another authority issues is named for who stated it
    (`sec_lei`), never for the issuer.
- **Fields:** use the kind's names. A list-shaped field has no contract
  syntax yet: leave it out, say so, and log a ticket.
- **Relationships:** type, the other end's key, the source it lives in,
  start and end. List every type the source carries. Label each mapped one's
  `scope` `<Provider> <relationship family>`.
- **A value of another kind** (an identifier of a different kind of entity)
  stays out of this kind; log it for that kind.
- **Provenance:** trace stays beside the record (operator, 2026-09-27).
  Capture hashes, run ids and sync times never go into `provenance`. Only
  the source's own record may, when the reader keeps it (`native_record`).
- **An unmapped source value:** first test whether configured `value`, paths,
  iteration or frozen references can preserve it. Map only evidence the
  tested reading emits. If the grammar cannot express it, record a minimal
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
- Check it: `files.source('<source>')` must equal what you passed to
  `files.dumps`.
- Write `source`, `bronze`, `execution`, `read` and `mdm` for a configured
  captured-file path. The source worker requires
  `execution: {profile: source.read, workers: 1, max_artifacts: 1}`; workers
  and max_artifacts may each be 1 or 2. Declare `read.limits.max_bytes` at
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
  date.

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

**Output:** `quality.yaml` that `files.source('<source>')` loads, with
`quality` inside each contract, and the data-quality skill's `QUALITY.md`.

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
   - Check the kind's merge rules accept the source. A source missing from
     `defaults.sources` fails its whole batch. Check `defaults.sources` (a
     kind with its own check in code, run it; see Examples). Adding a source to an
     existing kind is a merge-rule change: log it for the operator.
   - **A new kind:** records are blocked with `classification_not_activated`
     until its classification rule is switched on. That is expected: the
     order below switches it on first. To see what it would do, add the
     verdict to a copy of the policy in memory only, and label that pass as
     a test input.
   - Run affected configured-engine and retained equivalence tests:
     `uv run --no-sync pytest -q <those files>`. Then prove the full installed
     parse → prepare → merge path on fresh PostgreSQL 16 with separate worker
     and verifier roles, destination fencing and unchanged replay. Record
     assertions, identities, quality counts and deferrals, not only row totals.
   - `normalize` runs the quality checks. Each record shows what they did
     under `provenance.quality`, and an `exception` raises
     `UnsupportedRecord("quality_<id>")`. Report the counts
     (`edgar_warehouse.mdm.clean.quality.counts(records, deferred)`) and up
     to 10 examples of each.
2. **A proving run, for anything that matches records.** For a new domain,
   nothing is switched on yet. So the run registers a **copy** of the
   policy, with the new rules added to `automatic_rules` and each stamped
   `approved_by: proving-run` and `reason: "Proving Run only; not an
   approval"`, in the disposable database only. The body the operator later
   approves differs only in those fields (an earlier proving run does
   exactly this; see Examples).

   Write it as a pytest file that uses the Clean MDM fixtures, and it gets
   its own disposable PostgreSQL 16:
   ```python
   from tests.integration import test_clean_mdm_postgres as core
   postgres = core.postgres    # starts a postgres:16 container, removes it after
   database = core.database    # a migrated MDM database for one test
   ```
   Run it with Docker (on macOS, Colima), and bound it:
   `DOCKER_HOST=unix://$HOME/.colima/default/docker.sock timeout -s KILL 600 uv run --no-sync pytest -q -s <file>`.
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
   - **Digest, before saving:**
     `from edgar_warehouse.bookkeeping.clean.config import digest`. Then
     `digest(files.load_source(Path("rules/sources/<source>/source.yaml")))`
     for a source, or `digest(files.policy())` for the merge rules. It is
     what `rules save` will store.
   - **Proof file:** JSON with `digest`, `batch_hash`, `passed`, `evidence`
     and `note`. `--proof-uri` is `file://<absolute path>` locally or
     `s3://…`, and `--proof-sha256` is the file's sha256.
   - **Version label:** `<source or kind>-<YYYY-MM-DD>.<short change name>`,
     e.g. `sec.submissions.person-2026-09-30.first`.
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
     `n`, `correct`, `lower_bound`, `adversarial` (`n`, `violations`),
     `cohort` (the sha256 of each input and script), `approved_by: null`,
     `approved_at: null` and a one-line `reason`.
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

Running the feed is the **bookkeeping** skill's **run** mode, with
`--source <name> --feed <feed>`. It submits `rules run --target <target>`
with an input manifest and its sha256. Run targets in their declared
dependency order, and report any missing worker as unfinished implementation.

## When a command is missing

This skill names some commands before they are built. When you reach one:
- if the step says what to do instead, do that in your scratchpad;
- if it does not, stop at that step and tell the operator.

Either way, write it in the log.

| Command | State | What to do | Built by |
|---|---|---|---|
| `rules check` | not built | Dry run by hand (**test**) | rules-skill ticket 03 |
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
- **Fields:** Company's are `FIELDS = CONTRACT["adapter"]["fields"]` in
  `edgar_warehouse/mdm/clean/company_source.py`; Person has none in code, so
  its consumer spec (`docs/specs/person/consumer.md`, "The Person
  projection") holds them. A list-shaped field: Person's `name_variants[]`.
- **Another kind's value:** a ticker belongs to Security, not Company.
- **Joining identifiers:** today `cik` and `lei`; the SEC-to-GLEIF name rules
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
- **Proving runs:** ticket 05's `.scratch/company-mastering/research/05_proving_run.py`
  (`candidate()` stamps the copied policy); ticket 27's
  `.scratch/company-mastering/research/27_proving_run.py` (6,726 records,
  about 25 minutes, a second pass that changes nothing).
- **Unfinished live pipelines:** Company catalog and census joins and GLEIF
  streaming were unfinished when this was written (see Codex's retirement
  tickets).
