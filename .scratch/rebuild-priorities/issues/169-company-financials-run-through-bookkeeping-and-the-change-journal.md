# 169: Company financials run through Bookkeeping and the Change Journal

Priority: 169. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 08:23 ET (operator, 2026-11-02: "Is company financial go through bookkeeping and change journal", then "What do we need to do to introduce bookkeeping and change journal in accordance with elimination of 7 wastes", then "Yes").

Type: task. Status: in progress (Claude, 2026-11-02 09:12 ET; operator: "Agreed" to start). Blocked by: none.

## Question

The company financials (facts, line items, measures) are built by hand: `rules/source-sequence.yaml` gives `sec.company-facts` `target: null` ("its silver landing target comes with ticket 46", never filled), the Bookkeeping feed test refuses its feed, and nothing records the facts files in the Change Journal. What does it take to run them as tracked work that skips unchanged files, without waste?

## The seven wastes, applied

| Waste | Here |
|---|---|
| Over-production | Only the three tables the product uses; no gold, no new target kind |
| Motion | The step order lives in the rules, not in a person's memory |
| Over-processing | The Journal skips an unchanged file; rules changes reprocess; ticket 48's proof is carried forward, not repeated |
| Waiting | The deadline is sized from one measured real run |
| Defects | The landing step writes the quality results file (ticket 165); bounds are checked first |
| Transport, Inventory | Existing `land` and silver commands; no copied captures; test stores and containers removed |

## Parts

- [x] GoF consult before any code (2026-11-02 09:12 ET): leave the target manifest and the worker registry; both are built for a new step ("a new profile is a new module and an entry in `PROFILES`; Bookkeeping does not change"); add, do not refactor
- [x] (slice 1: read and land; line items and measures are slice 2) `sec.company-facts` gets one Bookkeeping target (`silver`) with three steps in order: land `company_fact`, line items, measures; each step reads the previous step's verified output (`run:` binding). The source sequence, the feed resolver and the load doc ("financial facts remain in their captured evidence") say so (2026-11-02 09:34 ET: target `silver`, steps `facts`, `land`, `processed`; `tests/mdm/test_company_facts_silver_target.py`, `tests/integration/test_silver_land_worker_postgres.py`; 150 unit and manifest tests pass)
- [x] The Change Journal records the captured facts files (2026-11-02 09:34 ET: the `processed` step; an unchanged repeat names no file, force names all, one changed file is the only one named); the processing identity is the digest of the facts, line-item and measure rules; no source-specific code in the Journal (its independence stays)
- [x] Whether line items and measures can rebuild only the Companies whose facts changed (2026-11-02 11:50 ET): no. Both tables are snapshots and the writer deletes every row a delivery lacks, even with `partition: company_key` declared, so a partial delivery would remove the other companies. The first version rebuilds both whole; a run starts only when the Journal names a changed file. A partition-scoped replace in the writer is the later change, not built (deferred to a new ticket if the timed run says it is needed)
- [x] (slice 2) Steps `line_items` and `measures` (`silver.derive`) between `land` and `processed` (2026-11-02 11:50 ET; `tests/integration/test_silver_derive_worker_postgres.py`: rebuild is repeatable, the verifier refuses a table that no longer matches its receipt, both builds need the master database; `tests/mdm/test_company_facts_silver_target.py`); if not, the first version rebuilds all and the ticket says why
- [x] (slice 1) A limited proof only: one Company's facts file, both orders, a second pass that changes nothing, an unchanged file skipped, a changed rule reprocessed. No full cohort rerun. Slice 1 done: a retry changes nothing and the verifier refuses when silver holds fewer keys
- [ ] ~~One real run is timed and its deadline sized from the measure (say the time before starting it)~~ deferred: the facts files are not on this machine and capturing them is a provider request needing separate permission; found 2026-11-02 17:46 ET
- [x] The landing step writes `QUALITY_RESULTS_FILE` (already: `land()` reads it from the environment for the land and both derive builds; nothing to build) (2026-11-02 17:46 ET)
- [x] First quality checks on `company_fact` (operator, 2026-11-02 17:46 ET: "Build the quality checks use the skill research data kitchen github"; research note `docs/research/datakitchen-testgen-test-types-2026-11-02.md`, DataKitchen TestGen tag 5.134.0): four `one_value` checks flagging a filing whose facts disagree on form, filing date, fiscal year or fiscal period (`tests/unit/test_company_facts_quality_checks.py`) (2026-11-02 17:46 ET)
- [ ] ~~Quality checks on `company_line_item` and `company_measure`~~ deferred to ticket 175: the engine's `in_set` reads text columns only (a check on `window_years`, a BIGINT, is refused by the catalog: "in_set reads a VARCHAR column"), and TestGen's other types (unique key, not null, bound, row condition, pattern, referential) need new check kinds
- [x] Stores and containers a test run leaves are removed (none left: docker lists only the catalog and shared stores, 2026-11-02 17:38 ET)
- [x] Learning → skill (2026-11-02 17:38 ET): `bookkeeping` names `silver.land` and `silver.derive`; `company-financials` names the target, steps and identity and the whole-rebuild limit; `data-platform/COMBINING.md` now says a per-unit numbered source name cannot run as a target (found in ticket 172); `change-journal` stays independent of workloads, so no line

## What I found (2026-11-02 09:12 ET)

Read-only, from the code. Bookkeeping and the Journal are already source-neutral; only the silver step is missing.

- A source declares its work as \`bookkeeping.targets\` in its \`source.yaml\`, as ordered steps (\`operation\`, \`requires\`, \`key\`, \`leases\`, \`checks\`). \`sec.company\` shows the shape: \`source.read\` steps, \`source.combine\`, \`mdm.prepare\`, \`mdm.merge\`, then \`journal.record\`.
- The operations that exist: \`artifact.copy\`, \`journal.record\`, \`mdm.merge\`, \`mdm.prepare\`, \`mdm.publish\`, \`provider.capture\`, \`source.combine\`, \`source.read\`. **There is no silver operation.** The "Bookkeeping silver-landing step" named in the map was never built.
- \`journal.record\` and \`changed_files\` are generic: the processing identity is the digest of the source's rules plus its shared inputs; the Journal skips a file recorded under the same identity and key and content hash. Nothing in them names a source, so company facts can use them unchanged as the last step.
- \`mdm/clean/target_manifest.py\` forms each step's units from the declaration by operation (\`FORMS\`), and "names nothing about a source or a kind".
- A worker is one module in \`edgar_warehouse/workers/\` plus an entry in \`PROFILES\`.
- Local silver: no silver connection is configured on this machine (the connection files only unset it), so an end-to-end test uses a Postgres test container (OrbStack works), like \`tests/integration/test_company_fact_silver.py\`.

## Slices (each ends with a limited proof, no cohort rerun)

1. **Land the facts.** New worker \`silver.land\` (reads a verified \`source.read\` output, calls \`silver_writer.land\`, writes the quality results file), its \`FORMS\` entry, a \`silver\` target on \`sec.company-facts\` with steps \`facts\` (source.read), \`land\` (silver.land), \`processed\` (journal.record). Proof: one Company's file, a second pass changes nothing, an unchanged file is skipped, a changed rule reprocesses.
2. **Derive line items and measures.** New worker \`silver.derive\` (calls \`line_items.build\` and \`measures.build\`), two more steps after \`land\`. First check whether they can rebuild only the Companies whose facts changed.
3. **Time one real run, then size the deadline**; add the first quality checks (operator decides them); update the sequence file, the load doc and the three skills.

## Slice 1 review (2026-11-02 09:38 ET)

Three-axis review of the first slice. Applied: the byte budget is spent across a unit's artifacts; the unused `restricted` argument is gone (the silver and master logins are the process's own `SILVER_DATABASE_URL` and `MDM_DATABASE_URL`); the receipt is built in the same pass that lands the rows (no second read); the verifier asks silver for the rows of the unit's own filers and refuses when a key is missing, so other units' rows cannot hide one (`test_other_units_rows_cannot_hide_a_missing_key`); a changed rule names every file again (`test_changed_rules_name_every_file_again`); dead test code removed.

Checked in the Bookkeeping SQL (`claim` in `001_control.sql`): a unit cannot be claimed while any unit of a required step is not verified, so `processed` waits for every `land` unit and a file is never recorded before it landed. The silver writer takes its own table lock, so two land units cannot write one table at once. "Both orders" does not apply here: silver land has no merge order; the proof is retry-safe and rule-sensitive.

Kept as judgement calls: three workers with similar execute/verify shapes are not yet a shared base; `max_artifacts: 512` and `workers: 1` copy the other sources and are re-sized from the timed run (parked ticket 170).

## Slice 2 review (2026-11-02 11:52 ET)

Three-axis review. Applied: (1) the leases were per output file, so two runs could rebuild or read one silver table at once; now each step leases the silver tables it writes and reads (`silver:{silver}`, `silver:{reads}`, taken from the unit's keys; `land` leases `company_fact`, `line_items` leases `company_line_item` and `company_fact`, `measures` leases `company_measure` and `company_line_item`), and the worker refuses a unit whose keys name other tables than its build; (2) the verifier only compared a table with a receipt taken from the same table, so a build that wrote nothing would pass; a build over a source that holds rows must now give rows, only for companies the source holds (checked at execute and at verify); (3) the snapshot claim is a test, not only a reading of the code (`test_a_snapshot_delivery_of_some_companies_removes_the_others`). Left (judgement calls): the shared receipt digest and `engines()` between the two silver workers wait for a third worker (GoF); the `if build` branch waits for a third build; the verifier does not recompute the arithmetic, the builds' own tests do.

`processed` waits for `measures` to be verified (`claim` in `001_control.sql` blocks a unit while any unit of a required step is unverified), and `measures` waits for `line_items`, which waits for every `land` unit.

