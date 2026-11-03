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
- [ ] Slice 1: a context value from the document's receipt (\`{receipt: sha256}\`, \`{receipt: key}\`)
- [ ] Slice 2: run facts and a run file's digest bound into a step's contract body (a declared token map), for reads and combines
- [ ] Slice 3: a shared run file enters the processing identity by a declared content projection (the census by entries, normalizers and version)
- [ ] Slice 4: lookup sets from a bundle's keys (a group larger than 16, or a keys unit that spans the bundle): measure the census read per group against the dedicated route's once per bundle, then choose
- [ ] Slice 5: the version 2 \`mastering\` target for \`sec.company\` (steps, run facts and files, lease sizes), plan tests and real workers on Postgres, the dedicated writer retired once \`load\` produces the same manifest
- [ ] Name Frequency: rebuild it from the whole captured population under the current rules (load sequence step 4), and record its digest
- [ ] The 10-minute slice: measure one bundle, then size \`--bundles\` and \`--workers\` from the cores and memory, and state the time of the whole load
- [ ] Learning → skill: \`skills/data-operations/SKILL.md\` names the version 2 requirement of \`load\` (done with this ticket's opening), and the sizing it measures here
