# 177: sec.company loads through the load command

Priority: 177. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 20:07 ET (operator, 2026-11-02: "yes run the 10 minute slice optimize using the skill").

Type: task. Status: open, not started. Related: [176](176-the-three-blocked-sources-are-wired-into-bookkeeping.md) (the other sources are wired), [172](172-the-thirteenf-securities-run-through-bookkeeping-and-the-change-journal.md) (the 13F target is the pattern).

## Question

`sec.company` is switched on in the new local store (`source-by-source`, 2026-11-02), but the generic `edgar-warehouse load` cannot plan it. Its first bundle stopped at `mdm prepare-capture` with "The source's Bookkeeping section must be version 2: each step's units and input"; every bundle of the first attempt stopped the same way, before any run was submitted. Every other source with a processing target is version 2. `sec.company` still uses the dedicated route (`mdm prepare-clean-company`, then `rules run`; docs/company-only-acquisition.md), which needs a population file, a Name Frequency census and the ticker catalog for each bundle of at most 512 Companies.

The plan over the retained capture (`sec.submissions.company/all-76230`) counts 76,231 documents. `execution.max_artifacts` is 2, which the generic route would turn into 38,116 bundles; the dedicated route uses 512.

## What is known (no request)

- The merge rules (`platform-2026-11-02.fresh-store`) and `sec.company-2026-11-02.fresh-store` are active in the new store; no Company is loaded.
- The census files on this machine are older proving artifacts; the load sequence requires Name Frequency from the whole population, rebuilt under the current rules.
- The machine has 8 cores and 8 GB (Docker's VM 4 GB); the data-operations skill says to measure one bundle first and to merge into shared masters one bundle at a time on this size.

## Parts

- [ ] Decide the route with the operator: a version 2 target the generic `load` runs (recommended: one command for every source, the Change Journal skip rule, resumable), or the dedicated route kept and documented
- [ ] Name Frequency: rebuild it from the whole captured population under the current rules (load sequence step 4), and record its digest
- [ ] The version 2 target for `sec.company` (run files for the population and census, the catalog, a bundle size that fits), plan tests and real workers on Postgres
- [ ] The 10-minute slice: measure one bundle, then size `--bundles` and `--workers` from the cores and memory, and state the time of the whole load
- [ ] Learning → skill: `skills/data-operations/SKILL.md` names the version 2 requirement of `load` (done with this ticket's opening), and the sizing it measures here
