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
never approve without a test run; no request to `sec.gov`; never read or
print a secret; never guess an identifier; never invent a command; ask one
question at a time, with your recommendation.

## The flow

| Step | Mode | Detail in |
|---|---|---|
| 0 | Setup, once per machine | this file |
| 1 | Onboard a new feed or kind | [data-onboarding](../data-onboarding/SKILL.md) |
| 1b | Change a live feed's rules | [refining-rules](../refining-rules/SKILL.md) |
| 2 | Parse: read captured files with the configured engine | this file, then [bookkeeping RUN](../bookkeeping/RUN.md) |
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
tables and the records set aside. Nothing feed-specific runs.

1. The feed's pipeline is saved, tested, approved and switched on (Mode 4).
2. Submit: `edgar-warehouse rules run --pipeline <name> --target <target> --input-manifest <uri> --input-sha256 <sha256>`.
   Keep the `run_id` it prints.
3. Work, as the worker login: `edgar-warehouse workers work source.read <run_id> --limit 100`.
4. Verify, as the verifier login (a different `BOOKKEEPING_CLEAN_DATABASE_URL`):
   `edgar-warehouse workers verify source.read <run_id> --reports <uri> --limit 100`.
5. Finish: `edgar-warehouse bookkeeping finalize <run_id>`. Done when
   `run.state` is `complete` and every unit is `verified`.

A step whose profile has no worker yet is a blocker to report, never a reason
to run the step some other way. `edgar-warehouse workers describe <profile>`
says whether a profile exists.

## 3. Master

Two worker profiles take parsed records into Clean MDM; a feed's rules file
names them in its `mdm` target (or a pipeline's).

- `mdm.merge`: one Clean MDM input manifest (contract version 2) through the
  Merge Stage. Its unit's input is that manifest; a batch's records file sits
  beside it. Its verifier reports `mdm.committed` after reading the batches
  back from MDM.
- `mdm.publish`: one committed batch to one consumer (`journal`, `export`,
  `graph`), in the consumer's generation order. Its unit's keys name the
  batch and the consumer. Its verifier reports `mdm.published`.

Before the first run, once per MDM database: `edgar-warehouse mdm migrate`,
then `edgar-warehouse bookkeeping init-guard --runtime-role <MDM application role>`
with `DESTINATION_MIGRATION_DATABASE_URL` set to the MDM database's owner,
since every MDM commit is checked against the worker's live lease. Then, for each profile, as in Parse:

1. Submit: `edgar-warehouse rules run --source <name> --target mdm --input-manifest <uri> --input-sha256 <sha256>`.
   An MDM target needs the operator's approval of that rules version first (Mode 4).
2. Work with the MDM application login in `MDM_DATABASE_URL` (and its role in
   `MDM_APPLICATION_ROLE`): `edgar-warehouse workers work mdm.merge <run_id> --limit 100`.
3. Verify with another login for both Bookkeeping and MDM:
   `edgar-warehouse workers verify mdm.merge <run_id> --reports <uri> --limit 100`.
4. The same for `mdm.publish`. One consumer takes one batch at a time, in
   order, so repeat work and verify until `edgar-warehouse bookkeeping status <run_id>`
   shows every unit `verified`.
5. Finish: `edgar-warehouse bookkeeping finalize <run_id>`.

A lost acknowledgement is harmless: the worker resumes the same MDM run, and
MDM never merges or publishes a batch twice. After a stop, use
`edgar-warehouse bookkeeping resume <run_id>` and run the workers again.

**Not built yet:** a configured step that turns a `source.read` reading into
an MDM input manifest (to-do 21, with the Company and GLEIF read blocks).
Until then the manifest comes from a feed's existing preparation.

## 6. Custom parsing

Only when the engine cannot state what a field needs. First check
[REFERENCE](../data-onboarding/REFERENCE.md) and the engine's primitives; a
custom step is the last resort (operator, 2026-10-03: "Write a step, then
stop").

This mode needs a checkout of the repository on your own branch, since a step
is code reviewed in a PR.

1. Write one plain function of one value in `edgar_warehouse/rules/steps.py`,
   registered in `STEPS` as `<name>@<version>`. It names no source or kind
   (`blank_missing_token@1` is the pattern).
2. Test it alone in `tests/engine/test_source_engine.py`: every value shape it
   accepts, and each one it refuses.
3. Call it from the feed's contract:
   `custom: {step: <name>@<version>, inputs: {value: <expression>}}`. The
   engine refuses a contract that names a step not in `STEPS`.
4. List the step in the feed's Mapping Document:
   `edgar-warehouse rules mapdoc write --only <source>`.
5. Run the feed's test run (Mode 4's evidence) with the step.
6. Open a PR with the step, its tests and the evidence. **Stop.** The operator
   reviews and approves the code and the rules version; never switch it on
   yourself.

## 7. Self-check

`edgar-warehouse doctor` is the skill checking itself. When it lists an
unresolved command, either the skill text or the command line is wrong: fix
the one that is wrong, in a PR, never by guessing a replacement. The same
check runs in CI (`tests/engine/test_data_skill_bundle_postgres.py`), so a
skill cannot ship naming a command that does not exist.
