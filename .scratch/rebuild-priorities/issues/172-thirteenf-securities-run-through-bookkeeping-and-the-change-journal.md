# 172: The 13F Securities run through Bookkeeping and the Change Journal

Priority: 172. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 12:15 ET (operator, 2026-11-02: "List all pipeline with no bookkeeping", then "first Bookkeeping ticket for sec.thirteenf.securities?").

Type: task. Status: closed incomplete (the timed real run is deferred). Blocked by: none ([173](173-the-thirteenf-source-is-named-for-what-it-masters.md), the rename, merged). Pattern: [169](169-company-financials-run-through-bookkeeping-and-the-change-journal.md) (company facts) and the `openfigi` and `sec.nport.security` mastering targets.

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

- [x] GoF consult before any code: the change is rules files and a test, no production code; the target copies the `openfigi` shape, so the verdict is leave it (2026-11-02 16:03 ET)
- [x] Find how the Securities are mastered today (the older prepare commands and the tests that use the reading), and what a data set's size does to the units (an output over 32 MiB is written in pieces, ticket 83): found that `reduce.yaml` named eight fixed units (`units_1..8`); a Bookkeeping slot is one name over every unit, so it is now `units` (2026-11-02 16:03 ET)
- [x] A `mastering` target in `source.yaml` (`read`, `reduce`, `combine`, `record`, `prepare`, `merge`, `processed`; `record.yaml` is the combined row itself); proved by `tests/mdm/test_thirteenf_securities_target.py` and the 13F chain tests run through `record.yaml` (2026-11-02 16:03 ET), shaped like `openfigi` and `sec.nport.security`: `read` (slices of the files), `reduce` (`source.combine` over every read unit, ticket 82), `combine` (`source.combine`), `records` (`mdm.prepare`, table `security`, dataset `sec.thirteenf.securities.v1`), `merge` (`mdm.merge`), `processed` (`journal.record`)
- [x] `source-sequence.yaml` gives it the target (it now sits after `openfigi`, before `sec.nport.security`); the sequence and engine-bundle tests that pin the order and status are updated; unit and engine-bundle tests run before the push (2026-11-02 16:03 ET)
- [x] A limited proof only: a few invented information-table files; a second pass changes nothing; an unchanged file is skipped; a changed reduce or combine rule names every file again; a CUSIP failing its check digit is a data quality exception, not a stop (ticket 79 ruling): proved at plan level (steps, second pass, changed rule) and by the 13F chain tests run through `record.yaml`; the check-digit set-aside is covered by the existing identifier-format tests (2026-11-02 16:03 ET)
- [x] The Mapping Document is regenerated if the rules change it; the mapping test passes (2026-11-02 16:03 ET)
- [x] Before the real run: the target runs through the real workers on Postgres (`tests/integration/test_thirteenf_securities_target_postgres.py`): three invented files, one read unit each, reduce over all three units (a CUSIP in two files counts both holdings), combine, record, prepare; a second pass redoes nothing (2026-11-02 16:51 ET)
- [x] Before the real run: the Dataset Contract code. Earlier note ("no Rules Database here") was wrong: the shared store's `worker.env` holds `RULES_DATABASE_URL`. Saved the source as `sec.thirteenf.securities-2026-11-02.bookkeeping` in the shared Rules Database, ran `rules test` on 2 invented files in a disposable store (passed: all steps incl. merge and journal verified, 2 Securities mastered, 1 CUSIP with a bad check digit set aside, second pass changed nothing), then approved it under "Approved the rules always" (2026-10-15) with that run as evidence. Switching it on in MDM still waits for the operator's words (2026-11-02 17:13 ET)
- [x] The rule is documented where it was missed: CLAUDE.md "Shared local data" and the `data-onboarding` skill's "test" mode (2026-11-02 17:13 ET)
- [x] Switched on in MDM (operator, 2026-11-02 17:23 ET: "A and B", to the offer to switch on `sec.thirteenf.securities` and defer the timed run): `rules activate` registered the approved version `sec.thirteenf.securities-2026-11-02.bookkeeping`; `rules status` shows it active (2026-11-02 17:23 ET)
- [ ] ~~One real run is timed and its deadline and `workers` sized from the measure (say the time before starting it; provider access is not needed: the files are already captured)~~ deferred (operator, 2026-11-02 17:23 ET: "A and B"): the 13F files are not on this machine and capturing them is a provider request needing separate permission; the lease and workers stay at the defaults until the run. Move to a new ticket when the files are available
- [x] Stores and containers a test run leaves are removed (none left: 2026-11-02 16:03 ET)
- [x] Learning → skill: the `security-master` skill names the three mastering targets and the 13F steps; `bookkeeping` and `change-journal` need no line (the target uses their existing operations) (2026-11-02 16:03 ET)
