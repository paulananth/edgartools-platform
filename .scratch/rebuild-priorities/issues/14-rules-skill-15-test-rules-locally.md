# Test a rules version locally, on a pinned capture, and record the run

Priority: 14, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/rules-skill/issues/15-test-rules-locally.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task
Status: claimed (Claude, 2026-10-18 ET; slice 1 on branch `claude/t14-rules-test-run`). The first design below (2026-09-29) predates the configured source chain; the 2026-10-18 design replaces it. The design and the facts below were written on
2026-09-29; no code was written. Kept as its own ticket (operator, 2026-10-02:
"agreed").
Blocked by: nothing (ticket 14 merged, #757)
Related: platform validation `05c-data-onboarding-skill-gaps.md` items 2 (a
proving run as a command), 3 (a command writes the input manifest) and 12
(what `batch_hash` covers). This ticket's `rules test` would close all three.

## Operator rulings

- "Rules can't be approved without test evidence, it can be overruled but
  test evidence must exist" (2026-09-29, ticket 14).
- "rules has to be tested localy" (2026-09-29): a version's test run is made
  on this machine, from files already captured; never from a live source,
  never evidence built by hand.

## Found (2026-09-29 21:00 ET)

- Nothing writes a test run today (ticket 14, step 1). `rules record-proof`
  records one someone else wrote; the Bookkeeping skill's "evaluator" does not
  exist.
- Local captures, `~/.local/share/edgartools/clean-mdm/research/`:
  - GLEIF Golden Copy 2026-09-11 16:00, the three members as captured
    (`gleif-20260911-1600/`, 979 MB; LEI2 sha256 `1b6cd9cd…a36a6a`).
  - SEC: only a derived extract (`rebuilt-2026-09-28/cm08-sec-scan.jsonl`)
    and SEC's ticker file. The raw submissions files are in bronze (S3);
    ticket 05's local copy of 7,000 was in a temporary folder and is gone.
- The production reading chains:
  - GLEIF: the Golden Copy zip, read by `gleif_source` / `prepare_native`.
  - SEC: bronze submissions JSON, then the warehouse's silver landing step
    run locally with the network blocked, then
    `company_source.prepare_company_bundle` (ticket 05 ran this chain).
  - Both end in `adapters.normalize` with the contract under test, which runs
    the quality checks and fixes (`quality.counts`).
- Ticket 22's proving run rebuilt the SEC landing row by hand: a copy of the
  reader, not the reader. A test run must run the production code.

- Checked (advisor, 2026-09-29 21:10 ET):
  - a run's input need not equal the test's batch: the Bookkeeping start
    only checks `batch_hash` is a well-formed reference
    (`engine.py`, `reference(... proof.batch_hash)`), so a test on a pinned
    sample authorizes runs on other batches;
  - the SEC reader needs GLEIF: `prepare_company_bundle` requires a Name
    Census built from the GLEIF archive and refuses one from another
    capture, so the SEC capture names the GLEIF capture it pairs with;
  - activation re-reads the test's manifest (`validation_proof` ->
    `artifacts.verified`, 32 MiB cap): the manifest is a small JSON list of
    files and sha256s, and it and the test run live under
    `~/.local/share/edgartools/clean-mdm/`, never a temporary folder.
- Reuse ticket 05's pinned SEC sample (`research/05-manifest.json`, 7,000
  bronze keys) and its network block (`05-bundles.sh`), so numbers stay
  comparable with tickets 05, 17 and 18.
- "What changes": the operator's Rules Database has no active version yet,
  so the first comparison is against the previous contract in git (for
  ticket 18: SEC v6 and the GLEIF contract before #753), named in the
  evidence.
- Size: a full Golden Copy is millions of records and Docker has 8 GB (a run
  was killed for low memory before). First run on 10,000 records, streamed,
  and tell the operator the projected full time before running it.

## Update (2026-10-02)

- Approvals have gone ahead with hand-built test runs, because `rules test`
  does not exist. The GLEIF parent approvals (platform validation 06a2,
  2026-10-01 22:21 ET) used an input list and two proof files written by hand
  from a test-run report, then `rules record-proof`. That is the gap this
  ticket closes.
- Ticket 18's versions, named above as the first target, have moved on. The
  first target is now the latest version of each source and of the merge
  rules when this ticket starts: today GLEIF `gleif-2026-10-01.parent-links`
  and the merge rules `platform-2026-10-01.gleif-parents`, plus Person feed 1
  (`sec.submissions.person-2026-10-01.first`).
- Since 2026-09-29: the schema is `mdm` (slice 3); the Rules Database can be a
  local throwaway (`rules-local-person-feed-1`); a test run's report shape is
  in `.scratch/platform-validation/research/06a2-report.json`.

## Design

1. **A pinned capture per source**, kept in
   `~/.local/share/edgartools/clean-mdm/captures/<source>/<name>/`, with a
   manifest naming each file and its sha256. GLEIF: the 2026-09-11 Golden
   Copy as it is. SEC: a pinned sample of bronze submissions files copied
   from S3 (reads only, never sec.gov), the same filers every time.
2. **`rules test --source <name> --version <v> --capture <manifest>`** runs
   the production reading chain for that version's contract on the capture,
   locally, the network blocked, and writes the test run:
   - `digest`, `batch_hash` (the capture manifest's sha256), `passed`;
   - `acquisition`: per feed, the capture manifest, the counts of each
     required producer (files captured, records read) and checks (every
     file's sha256 matches, every file read);
   - `evidence`: counts per outcome (records read, set aside by reason, each
     quality check and fix) with up to 10 examples each, and what changes
     against the active version on the same capture (records whose values
     change, with examples);
   - `note`: one line.
   It then records the run (`Rules.prove`). `passed` is false when a record
   fails in a way the contract does not allow, or a file is missing.
3. **Merge rules** (after the sources are tested and approved): the whole-policy test of a merge version is its rules'
   own proofs (`check_policy`) plus a local run of the pinned SEC and GLEIF
   captures through the Merge Stage on a throwaway PG16 (match counts before
   and after, with examples). Built after sources.
4. **Skill:** step 10's `record-proof` becomes `rules test`.

## Design (2026-10-18, replaces the one above)

Operator's ruling on ticket 12: "rules test first, fold the rest (Recommended)".

- **One declaration.** A source's chain is its `bookkeeping.targets.mastering` in `source.yaml` (read, combine, prepare, merge steps), the same target the AWS worker runtime runs (ticket 71). No second chain format. Today only SEC Company and SEC Person declare one; each other source gets its target as its first `rules test` run.
- **`edgar-warehouse rules test --source <name> --capture <manifest> --database env:<VAR> [--sample N] [--out <report>]`** submits the target to Bookkeeping in-process on the given PostgreSQL (refused when it already holds MDM records, unless `--fresh`), drives every step with the production workers and verifiers, runs the merge twice, and writes a counts-only report: records read and set aside by reason, each quality check, bound, waiting and decisions per source, identifiers on two entities, whether the second pass changed nothing, the policy and contract digests, and the capture manifest's sha256. No Docker in the command; no test helper imported.
- **Recording.** When `RULES_DATABASE_URL` is set, the report is recorded as the version's test run (`Rules.prove`); without it the report file is the evidence, as today.
- **Acceptance.** OpenFIGI on ticket 80's cohort reproduces `.scratch/onboarding/security-source-order/proving-run.json` count for count; then 13F; then each one-off Proving Run script is marked superseded.
- **Acceptance, corrected (2026-10-18 18:04 ET).** `proving-run.json` comes from a two-source run: it masters N-PORT's Securities first, then applies OpenFIGI onto them, and OpenFIGI creates no Security, so OpenFIGI alone on fresh stores binds nothing. Upstream rules are proved on their step and preparation output (operator's standing rule), so slice 2's acceptance is OpenFIGI's own chain output, `.scratch/onboarding/openfigi/openfigi-run.json` (per contract: outcome, filled, differences from the direct count). The merge comparison waits for N-PORT to declare its target. The five rules the old script switched on in a policy copy are all in `automatic_rules` now.

### Slice 1 as built (2026-10-18)

- `rules test --source --capture --documents --capture-run --as-of --stores <folder> --out [--minutes]` runs on the disposable local stores (`local-test-stores.py up <name>`), not on a database address: the stores' duty files give each step's worker, verifier and governance their own login, so each step runs as production runs it, in its own process. The command starts no container.
- It registers the source's Dataset Contracts and the Mastering Policy under a sandbox authority that names the capture (never an approval), saves, proves and activates a Bookkeeping-only Rules version in the throwaway Rules store, then runs the target twice (the second names every document again, `force`) and writes the counts-only report. Refused when the MDM store already holds records.
- `passed`: records reached MDM, no identifier sits on two masters, and the second pass changed nothing (every count, and an md5 of every current record's body, equal after both passes).
- Not yet in the report, against the design: each quality check's counts and the per-contract digests (it has the whole `source.yaml` digest and the policy digest). Slice 2.
- Code: `edgar_warehouse/rules/proving.py` (named so pytest never collects it). A failed step's message, which can hold a login, goes to `rules-test-errors.log` (mode 600) in the stores folder, never the screen; each command has the run's deadline.
- Recording the report as the version's test run (`Rules.prove` on the operator's Rules Database) is left to slice 2, with the generic manifest writer.

## Checklist

- [x] Ticket 12's ruling recorded; ticket 16's items 1, 2, 3 and 8 moved here, 5 deferred, 7 struck (2026-10-18 14:00 ET)
- [x] Found (2026-10-18 14:00 ET): running a declared target needs an input manifest (`{version: 2, steps: {<step>: [units]}}`). `capture_prepare.write_capture_manifest` writes one for any source whose reading keeps each document whole (read, records, merge: SEC Person); SEC Company has its own writer (`company_prepare.write_company_manifest`); no other source has one, and none declares a `mastering` target. Starting a run also resolves an active rules version (`Rules.save`, `prove`, `activate`, `resolve`), so a local test run needs a Rules Database too (a throwaway schema on the given PostgreSQL)
- [x] Found (2026-10-18 18:04 ET): OpenFIGI's record step reads each piece of the combine's output, a count known only after the combine runs, while Bookkeeping freezes every unit before the run; no worker emits the engine's sealed expansion. Raised as ticket 111 (a step reads a reading in pieces, `source.read` version 4)
- [x] GoF consult on slice 2 (2026-10-18 18:00 ET): the writer's unit plan goes in the Bookkeeping section (a new section version; two optional step keys the writer reads and strips before the engine sees the target); unit forms limited to those the code uses (byte slices up to `max_artifacts`, N interleaved groups, one); prove it gives `capture_prepare`'s manifest for SEC Person, then delete `capture_prepare`; leave `company_prepare` until the writer can state it
- [x] Found (2026-10-18 18:26 ET): a composed input names at most 16 prior units by slot, nested once, and each OpenFIGI answers file needs its own lookup set from its own request reading, so an answers unit holds at most 16 files (no quadratic re-read either). The full capture has 3,837 CUSIP and 3,877 ISIN request files: about 240 answers units per kind, under a list slot's 256. `reduce.yaml` named its readings one by one (`answers_1`..`answers_8`), and a combine took one reading per name: raised as ticket 112 (a name lists many readings). OpenFIGI's reduce then names `answers` once: a new OpenFIGI version, in slice 2
- [ ] A generic input-manifest writer for a target whose steps read with context and lookups, reduce and combine (what each onboarding's Proving Run script builds by hand today), driven by the target's declaration; or, if the declaration cannot state a step, a ticket for that gap
- [x] Advisor (2026-10-18 17:16 ET); `/gof-refactor-reviewer` ran as the review's GoF axis, after the code, not before
- [ ] Pin the GLEIF capture's manifest; copy and pin the SEC sample.
- [x] Slice 1: `rules test` for a source whose reading keeps each document whole (SEC Person), on the local stores; `tests/integration/test_rules_test_run_postgres.py` (2 passed, 66 s, real PG16) (2026-10-18 17:15 ET)
- [x] Found (2026-10-18 17:12 ET): the first run's invented people were all held back because the shared test helper gives every document a company's structure (SIC, EIN, state of incorporation, fiscal year end), which the Person rule rightly reads as a company. With a person-shaped document (`sec_capture.person`): 3 Person masters bound by CIK, the company-shaped name held back as entity undetermined, second pass unchanged, 29 s
- [x] Slice 1: `duties()` honours the duty files' `unset` lines (each file unsets nine other logins), so no login leaks in from the caller's shell; `tests/unit/test_rules_test_run.py` (3 passed) (2026-10-18 17:21 ET)
- [x] Slice 1: three-axis review (2026-10-18 17:23 ET). GoF (also standing in for the pre-code consult, which was skipped): leave it, no duplicate of production code. Standards and Spec: fixed a step's message reaching the screen, no per-command timeout, an undisposed engine, a module name pytest collects, a count-only idempotency check (now an md5 of every current record too), no check that pass 2 did work, an invented digest for a missing receipts file; unit 4 passed, integration 2 passed (66 s)
- [x] Slice 1: PR, CI, merge (#1091 merged 2026-10-18 17:37 ET; the first CI run failed the skill genericity lint, fixed by writing the skill line in kind-neutral words)
- [ ] ~~Recording the report as the version's test run (`Rules.prove`) and the skill's `record-proof` step becoming `rules test` for every source~~ deferred to slice 2: only SEC Person can run `rules test` until the generic manifest writer exists
- [ ] Run it on GLEIF and SEC for ticket 18's versions; the operator reads
      the evidence.
- [ ] Merge version test (step 3).
- [ ] Three-axis review, PR, CI; merge on the operator's word.
- [x] Learning → skill (slice 1, #1091): data-onboarding SKILL.md, Proving Run step: a source with a declared `mastering` target runs `rules test`; invented documents need the kind's own shape (`sec_capture.person`)
