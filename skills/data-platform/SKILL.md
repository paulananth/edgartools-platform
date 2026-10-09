---
name: data-platform
description: The whole data skill, installed as one package. Use it to set up a machine, then to take a feed from its captured files all the way through - onboarding its rules, parsing it with the configured engine, mastering it into Clean MDM - and to write a custom parsing step only when the engine cannot state something. Start here; it sends you to data-onboarding, refining-rules, bookkeeping or change-journal for each step's detail.
---

# Data Platform

One installed package, `edgartools-data`, holds everything this skill runs:
the rules creator, the configured engine, the workers, Bookkeeping, the
Change Journal, Clean MDM, and these skills. No checkout of the repository is
needed, except to write a custom parsing step (Mode 6).

## Hard stops

The [data-onboarding hard stops](../data-onboarding/SKILL.md#hard-stops) apply
to every mode here. In short: never approve or switch on for the operator;
never approve without a test run; no request to a provider the operator ruled out; never read or
print a secret; never guess an identifier; never invent a command; ask one
question at a time, with your recommendation.

## The flow

| Step | Mode | Detail in |
|---|---|---|
| 0 | Setup, once per machine | this file |
| 1 | Onboard a new feed or kind | [data-onboarding](../data-onboarding/SKILL.md) |
| 1b | Change a live feed's rules | [refining-rules](../refining-rules/SKILL.md) |
| 2 | Parse: read captured files with the configured engine | this file, then [bookkeeping RUN](../bookkeeping/RUN.md) |
| 2b | Combine keyed collections and join configured readings | [COMBINING.md](COMBINING.md) |
| 3 | Master: the parsed records into Clean MDM | this file |
| 4 | Approve and switch on | [APPROVE](../data-onboarding/APPROVE.md) |
| 5 | Recover a run | [bookkeeping RECOVERY](../bookkeeping/RECOVERY.md), [change-journal](../change-journal/SKILL.md) |
| 6 | Custom parsing, only when the engine cannot state a field | this file |
| 7 | Self-check | this file |

## 0. Setup

1. **Install.** The engine is Rust: `cargo` must be on the path (install it
   from rustup.rs if `cargo --version` fails). Pick the git ref to install
   (a commit on `main`), then:

   ```bash
   REF=<commit>
   REPO=git+https://github.com/paulananth/edgartools-platform@$REF
   uv tool install --python 3.12 "edgartools-data @ $REPO#subdirectory=packages/data-skill" \
     --with "edgartools-bookkeeping @ $REPO#subdirectory=packages/bookkeeping" \
     --with "edgartools-change-journal @ $REPO#subdirectory=packages/change-journal" \
     --with "source-contract @ $REPO#subdirectory=crates/source-contract"
   ```

   Building the engine takes about two minutes. It worked when
   `edgar-warehouse --help` lists `rules`, `bookkeeping`, `mdm`, `workers`,
   `plan` and `doctor`.

2. **Skills and rules folder.** `edgar-warehouse skill install --rules <new folder>`
   copies these skills into `~/.agents/skills` and `~/.claude/skills`, and the
   rules the bundle was built with into the new folder. It refuses to replace
   a skill it did not install (an older `link.sh` link): remove that link
   first, or keep using the linked copy. Then
   `export EDGAR_RULES_ROOT=<that folder>`. Without it, the bundle reads its
   own read-only copy of the rules.

3. **Stores.** Four PostgreSQL 16 databases, each set by its variable; never
   paste an address into the chat:
   `RULES_DATABASE_URL`, `BOOKKEEPING_CLEAN_DATABASE_URL`,
   `CHANGE_JOURNAL_DATABASE_URL`, `MDM_DATABASE_URL`. Their schemas:
   `edgar-warehouse rules init`, `edgar-warehouse bookkeeping init --runtime-role <role>`,
   `edgar-warehouse change-journal init --runtime-role <role>`,
   `edgar-warehouse mdm migrate`. The roles and the migration addresses are in
   [data-onboarding](../data-onboarding/SKILL.md) (Rules Database) and
   [bookkeeping](../bookkeeping/SKILL.md) (init, migrate).

4. **Check.** `edgar-warehouse doctor` must print `"ok": true`. It lists any
   command a skill names that does not exist, whether the engine loads, the
   rules folder in use, and which stores answer (`not set` is fine for a store
   the task does not use).

## 2. Parse

A feed is parsed by the `source.read` worker: the configured engine reads
each captured file by the feed's contract (its `read:` block) and writes the
tables and the records set aside. Nothing feed-specific runs. Read
[Configured reading](READING.md) before writing the contract: it covers
complete JSON records, column arrays, exact source text and frozen references.

1. The feed's pipeline is saved, tested, approved and switched on (Mode 4).
2. Submit: `edgar-warehouse rules run --pipeline <name> --target <target> --input-manifest <uri> --input-sha256 <sha256>`.
   Keep the `run_id` it prints.
3. Work, as the worker login: `edgar-warehouse workers work source.read <run_id> --limit 100`.
4. Verify, as the verifier login (a different `BOOKKEEPING_CLEAN_DATABASE_URL`):
   `edgar-warehouse workers verify source.read <run_id> --reports <uri> --limit 100`.
5. Repeat work and verify until every read unit is verified; the limit bounds
   one invocation. For a read-only target, finish with
   `edgar-warehouse bookkeeping finalize <run_id>` and check `run.state` is
   `complete` with every unit `verified`. For a combined target, continue the
   **same run_id** through Master; finalize after all declared steps verify.

A step whose profile has no worker yet is a blocker to report, never a reason
to run the step some other way. `edgar-warehouse workers describe <profile>`
says whether a profile exists.

## 3. Master

Three worker profiles take parsed records into Clean MDM; a feed's rules
file names them in its `mdm` target (or a pipeline's), after its `source.read`
step:

- `mdm.prepare`: a `source.read` reading into a Clean MDM input manifest. Its
  unit's keys say which `table` of the reading, which MDM `dataset` (source
  code) reads the rows, the `policy` digest the batches pin, the `consumer`
  they advance (its own, from checkpoint 0), a `batch_id` prefix and the
  `as_of` instant. Optional `record_column` selects an object-valued column
  containing the complete source record; omitted, the table row is the record.
  Optional `effective_column` names a column holding the file's effective
  time: an ISO 8601 instant with a timezone, written the same way in every
  row of one file and no later than `as_of` (MDM would leave later records
  out). Its publications state it, so MDM dates the records, and a link
  restated by each file starts when first stated, with `last_seen` when last
  stated. Omitted, records carry no time, and a link with no stated start
  makes no link (`unknown_relationship_start`). When the file itself states
  no such instant, take it from the caller: declare a `context` text field in
  the reading, add the column `{context: {name: <field>}}`, and give each
  file its own context receipt ([READING.md](READING.md), "Artifact context
  and first-N rows").
  See [READING.md](READING.md) for shape checks. Records files of at most 1,000 rows sit beside the
  manifest. Its verifier rebuilds them and reports `mdm.prepared`.
- `mdm.merge`: one Clean MDM input manifest (contract version 2) through the
  Merge Stage; its verifier reads the batches back from MDM and reports
  `mdm.committed`.
- `mdm.publish`: one committed batch to one consumer (`journal`, `export`,
  `graph`), in the consumer's generation order. Its unit's keys name the
  batch and the consumer. Its verifier reports `mdm.published`.

A unit's input names the step before it (`{"from": {"step": "read", "key": ...}}`
in a version-2 input manifest), so one run goes read → prepare → merge →
publish.

Before the first run, once per MDM database: `edgar-warehouse mdm migrate`,
then `edgar-warehouse bookkeeping init-guard --runtime-role <MDM application role>`
with `DESTINATION_MIGRATION_DATABASE_URL` set to the MDM database's owner,
since every MDM commit is checked against the worker's live lease. Then, for each profile in step order, as in Parse:

1. For a combined run already submitted in Parse, retain its `run_id` and
   continue its declared steps. Otherwise submit:
   `edgar-warehouse rules run --source <name> --target mdm --input-manifest <uri> --input-sha256 <sha256>`.
   An MDM target needs the operator's approval of that rules version first (Mode 4).
2. Work and verify **each declared profile in dependency order**: `source.read`,
   `mdm.prepare`, `mdm.merge`, then each declared `mdm.publish` step. For example:
   `edgar-warehouse workers work mdm.prepare <run_id> --limit 100`, then
   `edgar-warehouse workers verify mdm.prepare <run_id> --reports <uri> --limit 100`.
   Use the worker Bookkeeping login for work and the separate verifier login
   for verify. For merge and publish, set `MDM_DATABASE_URL` to the MDM
   application login for work (`MDM_APPLICATION_ROLE` names its role), and to
   the separate MDM verifier login for verify.
3. Repeat work and verify for each profile until its units are verified.
   `--limit 100` bounds one invocation; it does not prove the whole step ran.
   One publication consumer takes one batch at a time, in generation order.
4. Finish: `edgar-warehouse bookkeeping finalize <run_id>`. Done when
   `edgar-warehouse bookkeeping status <run_id>` shows the run complete and
   every declared unit verified.

A lost acknowledgement is harmless: the worker resumes the same MDM run, and
MDM never merges or publishes a batch twice. After a stop, use
`edgar-warehouse bookkeeping resume <run_id>` and run the workers again.

### Examples: current source qualification

Person has a configured complete-JSON read
block in `sec.submissions.person/source.yaml`. Its installed PostgreSQL 16
trial proves read → prepare → merge with the actual Person Dataset Contract
and policy, preserving two fixture records; a separate 1,000-capture comparison
proves retained outcomes and assertion identities. These are qualification
results, not operator activation. Company raw columns and filing arrays are
qualified components; its catalog/census joins and complete source read block
remain unfinished. GLEIF still requires bounded archive streaming. Use only
pipelines whose every profile resolves with `workers describe`; a declared
Company acquisition or silver step without a worker remains incomplete.

## 6. Custom parsing

Only when the engine cannot state what a field needs. First check
[REFERENCE](../data-onboarding/REFERENCE.md) and the engine's primitives; a
custom step is the last resort (operator, 2026-10-03: "Write a step, then
stop").

This mode needs a checkout of the repository on your own branch, since a step
is code reviewed in a PR.

1. Write one plain function of one value in `edgar_warehouse/rules/steps.py`,
   registered in `STEPS` as `<name>@<version>`. It names no source or kind
   (`epoch_microseconds@1` is the reviewed-trial pattern).
2. Test it alone in `tests/engine/test_source_engine.py`: every value shape it
   accepts, and each one it refuses.
3. Call it from the feed's contract:
   `custom: {step: <name>@<version>, inputs: {value: <expression>}}`. The
   engine refuses a contract that names a step not in `STEPS`.
4. List the step in the feed's Mapping Document (the generated **Custom Parsing**
   sheet lists every custom expression and its rules path):
   `edgar-warehouse rules mapdoc write --only <source>`.
5. Run the feed's test run (Mode 4's evidence) with the step.
6. Open a PR with the step, its tests and the evidence. **Stop.** The operator
   reviews and approves the code and the rules version; never switch it on
   yourself.

### Trial evidence

`tests/engine/test_custom_parsing_trial.py` compares the generic timestamp-to-integer
step with an existing release-sequence calculation (one source's own), including negative
epochs, offsets and microseconds. It first demonstrates that the configured
`date` returns text and `number` cannot convert a timestamp. The installed-bundle
test repeats parse → prepare → merge with the custom expression and a separate
verifier. This is a review trial; no active source version names the step.

## 7. Self-check

`edgar-warehouse doctor` is the skill checking itself. When it lists an
unresolved command, either the skill text or the command line is wrong: fix
the one that is wrong, in a PR, never by guessing a replacement. The same
check runs in CI (`tests/engine/test_data_skill_bundle_postgres.py`), so a
skill cannot ship naming a command that does not exist.
