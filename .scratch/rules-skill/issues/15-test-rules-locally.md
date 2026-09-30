# Test a rules version locally, on a pinned capture, and record the run

Type: task
Status: in progress (Claude, branch `claude/rules-15-local-test`, 2026-09-29)
Blocked by: nothing (ticket 14 merged, #757)
Blocks: the first approvals on evidence: ticket 18's GLEIF and SEC source
versions, and the merge version that switches the two name rules on

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
- Size: a full Golden Copy is millions of records and Colima has 8 GB (a run
  was killed for low memory before). First run on 10,000 records, streamed,
  and tell the operator the projected full time before running it.

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

## Checklist

- [ ] Advisor, then `/gof-refactor-reviewer` before code.
- [ ] Pin the GLEIF capture's manifest; copy and pin the SEC sample.
- [ ] `rules test` for a source; unit tests on a tiny pinned capture.
- [ ] Run it on GLEIF and SEC for ticket 18's versions; the operator reads
      the evidence.
- [ ] Merge version test (step 3).
- [ ] Three-axis review, PR, CI; merge on the operator's word.
