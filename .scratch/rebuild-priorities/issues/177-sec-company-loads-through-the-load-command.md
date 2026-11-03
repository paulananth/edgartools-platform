# 177: sec.company loads through the load command

Priority: 177. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 20:07 ET (operator, 2026-11-02: "yes run the 10 minute slice optimize using the skill").

Type: task. Status: open (in progress). Related: [176](176-the-three-blocked-sources-are-wired-into-bookkeeping.md) (the other sources are wired), [172](172-the-thirteenf-securities-run-through-bookkeeping-and-the-change-journal.md) (the 13F target is the pattern).

## Question

`sec.company` is switched on in the new local store (`source-by-source`, 2026-11-02), but the generic `edgar-warehouse load` cannot plan it. Its first bundle stopped at `mdm prepare-capture` with "The source's Bookkeeping section must be version 2: each step's units and input"; every bundle of the first attempt stopped the same way, before any run was submitted. Every other source with a processing target is version 2. `sec.company` still uses the dedicated route (`mdm prepare-clean-company`, then `rules run`; docs/company-only-acquisition.md), which needs a population file, a Name Frequency census and the ticker catalog for each bundle of at most 512 Companies.

The plan over the retained capture (`sec.submissions.company/all-76230`) counts 76,231 documents. `execution.max_artifacts` is 2, which the generic route would turn into 38,116 bundles; the dedicated route uses 512.

## What is known (no request)

- The merge rules (`platform-2026-11-02.fresh-store`) and `sec.company-2026-11-02.fresh-store` are active in the new store; no Company is loaded.
- The census files on this machine are older proving artifacts; the load sequence requires Name Frequency from the whole population, rebuilt under the current rules.
- The machine has 8 cores and 8 GB (Docker's VM 4 GB); the data-operations skill says to measure one bundle first and to merge into shared masters one bundle at a time on this size.

## What the dedicated writer does that the version 2 planner cannot (read 2026-11-02 20:10 ET)

`edgar_warehouse/mdm/clean/company_prepare.py` builds the bundle in Python. Its steps (\`main\`, \`keys\`, \`catalog\`, \`census\`, \`combine\`, \`records\`, \`merge\`, \`processed\`) map onto version 2 steps. Four things do not:

1. **The receipt's hash as context.** Each main document's context holds \`raw_object_id\`, the document's receipt sha256 (and its key as \`bronze_object\`). Version 2 context takes only templates over the key and run facts.
2. **Run facts bound into a contract's body.** \`combine-census-captured.yaml\` and \`census.yaml\` carry placeholder tokens (the approved Company capture run, the approved catalog run, the census digest) that the writer replaces before it freezes the contract. A version 2 step can fill a fact into a read's context, not into a contract.
3. **The census as a shared input.** The writer checks the census against the capture's receipts and the population, binds its digest, and puts its content digest (entries, normalizers, version: not the capture it came from) into the processing identity beside the catalog's. A version 2 run file adds its whole-file digest.
4. **Lookup sets from the bundle's keys.** The census is read once, narrowed by the bundle's name and CIK keys (one keys reading of up to 512 documents). A version 2 lookup reads the same file's unit of an earlier \`each\` step, in groups of at most 16.

## Slices (each its own PR, with the GoF consult, a failing test first and CI)

Version 2 is generic; none of these may name Company.

## Parts

- [ ] Decide the route with the operator: a version 2 target the generic \`load\` runs: "yes convert sec.company to version 2" (operator, 2026-11-02 20:10 ET)
- [x] Gap analysis against the dedicated writer (2026-11-02 20:10 ET; the four gaps above)
- [x] Slice 1 (PR #1321, merged 2026-11-02): a context value from the document's receipt (\`{receipt: sha256}\`, \`{receipt: key}\`)
- [x] Slice 2 (PR #1322, merged 2026-11-02; tests/mdm/test_bind_run_inputs.py): run facts and a run file's digest bound into a step's contract body (a declared token map), for reads and combines
- [x] Slice 3 (2026-11-03 09:01 ET): a target's `run.projections` names, per run file, the top-level parts that enter the processing identity (the Name Count by entries, normalizers and version); the rest of the file moves nothing. Failing before: all 8 cases of tests/mdm/test_run_file_projection.py ("A target's run names its facts and files" refused the key). tests/mdm, tests/unit, tests/architecture pass (2419).
- [x] Slice 4 (2026-11-03 09:24 ET): measured on the 6.3 MB Name Count (43,245 entries) with the real engine: one read takes 0.56 s whether it is narrowed to 16 or 512 names, so the cost is the file, not the keys. Per group of 16 files the whole load (76,231 documents) would read it 4,765 times, about 45 min of one core; once per 512-file bundle it reads it 149 times, about 1.4 min. Chosen: a lookup with `over: all` reads every unit of its prerequisite (at most 256) in one reading, so the Name Count is read once per bundle like the dedicated route. Failing before: the two cases in tests/mdm/test_read_units.py ("over" refused by the lookup check). tests/mdm, tests/unit, tests/architecture pass (2421).
- [x] Slice 5a (2026-11-03 09:47 ET): a read step's `input.runfile: <name>` reads a run file's canonical bytes as the step's one document (the Name Count is a run file, not a captured document: gap 5 of the writer). Failing before: 3 cases in tests/mdm/test_bind_run_inputs.py ("A step's input names ... only"). tests/mdm, tests/unit, tests/architecture pass (2425)
- [ ] Slice 5: the version 2 \`mastering\` target for \`sec.company\` (steps, run facts and files, lease sizes), plan tests and real workers on Postgres, the dedicated writer retired once \`load\` produces the same manifest
- [ ] Name Frequency: rebuild it from the whole captured population under the current rules (load sequence step 4), and record its digest
- [ ] The 10-minute slice: measure one bundle, then size \`--bundles\` and \`--workers\` from the cores and memory, and state the time of the whole load
- [ ] Learning → skill: \`skills/data-operations/SKILL.md\` names the version 2 requirement of \`load\` (done with this ticket's opening), and the sizing it measures here
