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
| Put a master data field in silver, alone or as a copy | Every master data field is on its master in MDM, and only there (operator, 2026-10-28: "all master data fields must be on mdm"; operator, 2026-10-28: "silver must not have duplicate fields, it contredits the data governance principle one system of record"): in the kind's fields and the Dataset Contract. A silver row holds the transaction's own facts and its link keys |

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
| `rules/sources/<source>/source.yaml` | The feed: `source`, `bronze` and `dataset_contracts` (one Dataset Contract per source code). Its `bookkeeping` section, which runs the feed into silver and MDM, belongs to the Bookkeeping skill. |
| `rules/source-sequence.yaml` | One line per source folder, naming its Bookkeeping target (or `null` when no target is registered yet) and preferred `after` order. Every folder needs both a `source.yaml` (even one that only names the source and reads nothing) and a sequence entry. Every source must declare its intended `bookkeeping.targets` in `source.yaml`; a missing target or `target: null` is an explicit unregistered/not-runnable gap to resolve before claiming a complete pipeline. `after` is not a runtime dependency. Suite tests walk both files. |
| `rules/sources/<source>/quality.yaml` | The feed's data quality checks and fixes |
| `rules/sources/<source>/silver-<table>.yaml` | A silver table spec, one file per table (silver target): reviewed in the PR, registered from this file |
| `rules/merge/kinds/<kind>.yaml` | A new domain's matching and merge rules (only when the kind is new) |
| `rules/sources/<source>/MAPPING.xlsx`, `rules/merge/kinds/<kind>.xlsx` | The Mapping Documents, generated for stewards (**metadata**) |
| The Data Catalog (OpenMetadata) | Every feed, dataset and MDM field, published from the files (**metadata**) |

When renaming an existing source identity, update its folder and `source:`
identifier, Dataset Contract IDs, source-sequence entry, Bookkeeping bindings,
cross-source references and generated Mapping Document together. Treat the
rename as a new Rules version; retain prior run/capture evidence under the
identity that produced it, and use the normal review and approval gates before
activation.

The files in `rules/sources/` show Dataset Contracts and publication rules.
For configured complete JSON source extract, find a feed that keeps each
document whole (`grep -l "format: json" rules/sources/*/source.yaml`, then
its `read:` block) and read [data-platform READING](../data-platform/READING.md). A declared target is
not evidence that its workers exist; check every profile before submitting.

## Two targets: MDM and silver

Every step says what differs for each target. Read [TARGETS.md](TARGETS.md) before **plan-parts**, and again at any step when the part's target is silver or both.

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
  variable is not set. Source the shared store's private `worker.env` for
  rules commands and `governance.env` for switch-on. Never print either
  file. A refused connection is a moved port
  ([LOCAL-TESTING](../data-platform/LOCAL-TESTING.md)).

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

### Built means ready to turn on

Operator, 2026-11-04: "when you build it you need all of this once proved it is just turn on and go".
A source or domain is **finished when it can be turned on with one command and no preparation**. Everything
else happens while building it, once:

- the limited test passed while building it, and its counts are in the ticket. Once the rules are merged on
  `main` they are final: a store needs no test run and no proof to activate them (operator, 2026-11-04: "you
  dont need proof to activate once the rules are finalized");
- the operator's words approve the exact version on that merge, kept in git in `rules/approvals.yaml`
  (`rules approvals write`, APPROVE.md): `rules load` approves it in any store;
- the run's inputs are named where the source declares them: each fact and file its target needs, how it is
  produced, and where its captured files are. Write how each is produced in a comment directly above the
  target; `scripts/run_inputs.py [source]` prints every target's facts and files with those comments, and for
  an input with none, the comment lines that mention it, or says that none does;
- the order it needs (the sources and the merge rules before it) is declared in the source sequence;
- the merge rules it relies on are proved and approved the same way.

Turning it on is then only: save the version from `main`'s files, approve it on its merge, activate it, load it. Finding a
missing proof, input or capture at switch-on means the build was not finished: go back and finish it, and say
what was missing in the ticket. A rules change makes a new version and a new proof only for what changed
([Run each long step once](#modes-in-order)); an unchanged proof is carried forward.

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
   (`edgar_warehouse/mdm/evidence.py`); a kind that is not there
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

Follow [MAP.md](MAP.md) in full when you reach this mode: research the source, infer each record type, ask the real decisions one at a time, then write `source.yaml` (and a kind file for a new domain).

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

For a platform-wide request, restoration, business naming, entity domains,
glossaries or quality-case publication, follow [Business catalog](CATALOG.md). Discover all entities, relationships
and source/standalone pipeline targets from configuration; omit `--only` when
regenerating the entire catalog's workbooks. Require native entity domains,
glossaries, meaningful business definitions/associations and named quality cases;
technical tables alone are incomplete. Apply one evidence-driven method to all
entities and fields, with no source-specific renaming code. Publishing metadata
does not run or activate a pipeline.

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
   workbook with the rules. The installed `edgartools-data` bundle includes
   these workbooks; for changes to catalog identities or merge rules, verify
   the installed bundle sees the committed Mapping Documents as well.
4. Before the PR, see what would be published:
   `edgar-warehouse rules catalog plan`. This runs
   offline.
5. After the PR is merged, publish to the catalog:
   `edgar-warehouse rules catalog publish`. It needs
   `OPENMETADATA_URL` and `OPENMETADATA_TOKEN`. Never print the token. If
   no catalog server is reachable, say so; do not skip it silently.

### test: run it on real captured files and record the result

Follow [TEST.md](TEST.md) in full when you reach this mode: qualify on captured files, run a proving run once for anything that matches records, then save and record the test run.

### approve: the operator decides

Follow [APPROVE.md](APPROVE.md). Explain in plain words, ask once, and
record their exact words.

### switch-on: activate, then hand the run to Bookkeeping

Activate as in [APPROVE.md](APPROVE.md), "Switch on". A source built as above needs nothing before this
step: if switching on needs a test, an input or a capture that does not exist yet, the build is not finished
("Built means ready to turn on").

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
| Preview (matches against a copy of MDM) | not built | A proving run on a disposable PostgreSQL 16 (**test**) | the rules skill |
| Silver writer to a warehouse store | not built: the writer lands on PostgreSQL 16 only | Land on PostgreSQL 16 (**Two targets**) | a warehouse sink ticket (plan decision 36) |
| Flat export of a nested part | not built | Land flat parts; record each nested part as a gap | a profiling follow-up |
| Silver output worker in a pipeline | built: a `silver.land` step lands a reading's table | Add the step after the merge that makes the master ids the rows link to (**Two targets**); `silver land` by hand only for a table whose source has no such step | none |

## Examples (this repo's sources)

These name today's sources only as examples; nothing above depends on them.

- **A provider ruled out:** SEC (`sec.gov`): never request it, nor its
  documentation. For an SEC feed, use the existing SEC contract and its
  comments, `docs/specs/`, and the published code sets.
- **Names:** GLEIF is one folder, `gleif`, for three files, with codes
  `gleif.level1.v1` and `gleif.relationships.v1`. SEC submissions feed
  Company (`sec.company`); Person from the same files is
  `sec.submissions.person` and `sec.submissions.person.v1`.
- **A record key's order:** GLEIF relationships: start, end, type.
- **Fields:** Company's are its contract reading's `fields` column
  (`rules/sources/sec.company/source.yaml`, and the Fields sheet
  of its `MAPPING.xlsx`); Person has none in code, so
  its consumer spec (`docs/specs/person/consumer.md`, "The Person
  projection") holds them. A list-shaped field: Person's `name_variants[]`.
- **Another kind's value:** a ticker belongs to Security, not Company.
- **Joining identifiers:** today `cik` (the one Identifier Contract); the SEC-to-GLEIF waterfall
  passes (`sec-gleif-name-city-or-postcode`) bind by name with their proofs.
- **Classification:** SEC types people and firms alike as `other`; the SEC
  Company contract names its rule under `adapter.classification`; a
  `company` verdict in a Person rule is deferred with `probable_kind`
  (`rules/merge/kinds/company.yaml`). `person-cik` on `cik` is shaped like
  `company-cik`. SEC submissions carry no effective date, so Company sets
  `allow_unknown_effective`.
- **A mastering target to copy:** `rules/sources/sec.submissions.person/source.yaml`,
  `bookkeeping.targets.mastering` (read, prepare, merge, with each step's
  units and input).
- **Platform facts the SEC Company chain needs:** its code reads the
  switched-on `sec-company-candidate` from the policy when it loads, so a
  proving run stamps it into its copy of the policy first (**test**); its
  preparation (`edgar-warehouse mdm prepare-capture --source sec.company`) reads the
  main documents and the exchange catalog; no file is needed (the waterfall pass pairs the stored
  Companies with GLEIF after the load).
- **Source checks in code:** for Company,
  `merge.check_company_sources(files.policy(), assertions)`.
- **Pinned digests:** `tests/mdm/` (757 tests, under a minute) holds them;
  Company's are layers in `tests/mdm/policy_layers.py` (`LAYERS`, newest
  first). N-PORT's registrant (2026-10-15) ran only the 43 tests that load
  the rules, and CI failed on four pinned digests.
- **Proving runs:** `.scratch/company-mastering/research/05_proving_run.py`
  (`candidate()` stamps the copied policy);
  `.scratch/company-mastering/research/27_proving_run.py` (6,726 records,
  about 25 minutes, a second pass that changes nothing).
- **Unfinished live pipelines** (the one list; other skills point here):
  live acquisition (`provider.capture`,
  #933, qualified offline) waits for the worker runtime on AWS.
  A source's pipes switch on over captured files without it (#1108).
