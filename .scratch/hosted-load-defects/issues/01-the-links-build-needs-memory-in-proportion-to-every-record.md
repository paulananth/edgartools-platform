# 01: The links build needs memory in proportion to every record that states a link

Status: open
Type: bug
Blocked by: none
Blocks: the hosted reload's finish on a small machine

Found 2026-11-25 on the hosted reload (all 47 steps done, 2026-11-25 03:22 ET): the finish's `silver links` was killed
for memory (`rc=-9`) in the loader container (3.9 GB), once per attempt, and it was killed the same way at 14:01 ET on
2026-11-24, before any Form ADV fund records existed. The links, evidence, path and `master_binding` tables stay empty
until it runs, so Gold and every adviser-to-fund link show nothing.

## Measured (counts only)

- The build reads every record that states a link: 504,359 records, 896 MB of text. By source (records, MB): N-PORT
  securities 246,369 and 418; Form ADV fund-filing records 170,157 and 245; OpenFIGI 10,259 and 125; N-CEN classes
  30,317 and 29; N-CEN funds 12,953 and 23; N-PORT funds 12,937 and 20; Form ADV filings 12,442 and 20; the rest under 20.
- Only the Form ADV records (270 MB of text, 186,553 records): 5.6 minutes, peak memory footprint 4.2 GB (1.8 GB
  resident); 143,281 links, 186,280 evidence rows. The time is almost all in the Rust link calculation (270 of 334 s);
  reading and parsing the records took 17 s. Memory is therefore about 15 times the text and grows with it, so the whole
  set needs about 13 GB.
- On an 8 GB Mac the same build reached a 12 GB footprint (swap 10 GB of 11 GB) and was still computing after 14 minutes.
  The last finish that completed on the hosted store (2026-11-23) took 29.6 minutes.
- Link types are not independent: the consolidation chain (`IS_DIRECTLY_CONSOLIDATED_BY`, `IS_ULTIMATELY_CONSOLIDATED_BY`)
  and `SUCCESSOR_ENTITY` read each other's links, so the records cannot be split by type alone. The largest single type
  (issued-by, N-PORT and OpenFIGI) is about 540 MB of text, so a split by type still needs about 8 GB.

## Checklist

- [x] Operator, 2026-11-25: "Fix it to use bounded memory (Recommended)", then "fix the links memory issue" (2026-11-25 07:46 ET)
- [x] GoF consult (agent `risky-reviewer`): no pattern; the split was read against the Rust calculation and is exact when each reported link goes to one part, the hierarchy and succession types share one, and the parts' results are ordered by id (2026-11-25 07:46 ET)
- [x] The bound: one part's records and the ends' masters. Records are spooled to disk by subject, folded in 64 parts, kept as what a link reads (its links, assertion and effective date), and calculated in 65 parts: one for the types that read each other's links, 64 by type and source master, which holds every record that states one link. The silver rows are spooled and written as they are read (2026-11-25 07:46 ET)
- [x] Test first: `tests/unit/test_links_portions.py`; on the code before it fails on import of the parts (no `portion_of`), and `test_a_table_with_no_check_is_written_as_its_rows_arrive` fails because the writer read every row first. Parts equal one whole calculation over revisions, shared evidence, two subjects of one master, a cycle, a succession, two targets and waiting links (2026-11-25 07:46 ET)
- [x] No Rust change was needed: the memory was the fields a link never reads, held three times (text, Python, Rust) (2026-11-25 07:46 ET)
- [x] Measured on the hosted store, read only: 416,934 links, 478,867 evidence rows and every waiting count equal to the stored build, the rows equal column by column; 12 GB became 1.4 GB peak in the loader image capped at 3 GB with the last build's links read, 22 minutes became 4.0 (calculation, landing apart) (2026-11-25 07:46 ET)
- [ ] The finish within its five-minute bound, landing included, read from the next hosted load: the proof wrote nothing; the calculation alone takes 4.0 of the 5 minutes
- [ ] MySQL reads the records whole still (it streams no table): the bound is PostgreSQL's
- [x] Found by the Spec review before the merge: the edit had deleted the binding's query (`WANTED`), which `tests/storage_adapters/test_master_binding_in_database.py` covers and was not run here before the PR; restored, and that file fails without it (`NameError`) and passes with it (2026-11-25 08:01 ET)
- [x] Storage adapters 45 and 36 passed (PostgreSQL, MySQL; 9 skipped as PostgreSQL's own), 253 unit and MDM, 21 integration (2026-11-25 07:46 ET)
- [x] Operator, 2026-11-25 08:01 ET: "send it through 7 wastes". Phases of 194 s on the hosted store: read the records 104, bind the ends 25, read the masters 19, calculate 19, fold 9, rows 3, spool and the rest 16. Over-processing, removed: fields no link reads, held three times, and every row held before one is written. Transport, left: the server sending only what a link reads (452 of 896 MB) reads in 78 s, four connections in 68 to 73: 26 to 36 s for an engine-only statement or four sessions, on this machine's network. Over-production: none built (no Rust change, no option, no second builder). Defects: the deleted binding query, below; the storage tests that cover a changed module run before its PR. Waiting: one test of the parts needs no store (2 s). Inventory: the proof's worktree, files and branch go with the merge (2026-11-25 08:01 ET)
- [x] Learning → skill: `data-operations/HOSTED-LOADS.md`, "The finish takes at most five minutes" (2026-11-25 07:46 ET)
