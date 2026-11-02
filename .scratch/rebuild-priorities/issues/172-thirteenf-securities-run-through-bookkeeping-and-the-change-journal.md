# 172: The 13F Securities run through Bookkeeping and the Change Journal

Priority: 172. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 12:15 ET (operator, 2026-11-02: "List all pipeline with no bookkeeping", then "first Bookkeeping ticket for sec.thirteenf.securities?").

Type: task. Status: open. Blocked by: [173](173-the-thirteenf-source-is-named-for-what-it-masters.md) (the rename). Pattern: [169](169-company-financials-run-through-bookkeeping-and-the-change-journal.md) (company facts) and the `openfigi` and `sec.nport.security` mastering targets.

## Question

`sec.thirteenf.securities` has a full reading (`read`, `reduce.yaml`, `combine.yaml`, `quality.yaml`) and a Dataset Contract (`dataset_contracts: sec.thirteenf.securities.v1`), but no `bookkeeping` section: `rules/source-sequence.yaml` gives it `target: null` (after `gleif` and `openfigi`), so its Securities are mastered by hand and no file is recorded in the Change Journal. What does a Bookkeeping target need, without waste?

## The seven wastes, applied

| Waste | Here |
|---|---|
| Over-production | Securities only (the holdings wait for the manager filings, ticket 79); no silver step, no holdings table |
| Motion | The step order lives in the rules: read, reduce, combine, prepare, merge, record |
| Over-processing | The Journal skips an unchanged file; a changed read, reduce, combine or quality rule reprocesses; no full data-set rerun for the proof |
| Waiting | The deadline is sized from one measured run; `workers: 2` is checked against it, not copied |
| Defects | Run the engine bundle and source-sequence tests the change can affect before the first push |
| Transport, Inventory | The existing workers only (`source.read`, `source.combine`, `mdm.prepare`, `mdm.merge`, `journal.record`); test stores and containers removed |

## Parts

- [ ] GoF consult before any code
- [ ] Find how the Securities are mastered today (the older prepare commands and the tests that use the reading), and what a data set's size does to the units (an output over 32 MiB is written in pieces, ticket 83)
- [ ] A `mastering` target in `source.yaml`, shaped like `openfigi` and `sec.nport.security`: `read` (slices of the files), `reduce` (`source.combine` over every read unit, ticket 82), `combine` (`source.combine`), `records` (`mdm.prepare`, table `security`, dataset `sec.thirteenf.securities.v1`), `merge` (`mdm.merge`), `processed` (`journal.record`)
- [ ] `source-sequence.yaml` gives it the target; the sequence and engine-bundle tests that pin the order and status are updated
- [ ] A limited proof only: a few invented information-table files; a second pass changes nothing; an unchanged file is skipped; a changed reduce or combine rule names every file again; a CUSIP failing its check digit is a data quality exception, not a stop (ticket 79 ruling)
- [ ] The Mapping Document is regenerated if the rules change it; the mapping test passes
- [ ] One real run is timed and its deadline and `workers` sized from the measure (say the time before starting it; provider access is not needed: the files are already captured)
- [ ] Stores and containers a test run leaves are removed
- [ ] Learning → skill: `bookkeeping`, `change-journal` and the securities skill name the target and its steps
