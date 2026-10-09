# 07 Readers and custom parsing steps per feed

Type: task. Phase: B. Blocked by: 01b inventory, Codex retirement merged. Map: [map](../map.md). Plan: [plan](../plan.md).

## Checklist

- [ ] ~~Wait for Codex's old-parser retirement gate~~ overruled by the operator, 2026-10-09 09:05 ET: "start ticket 07 now" (the gate is still open: `.planning/workstreams/whole-source-census/TICKET.md`, 6,414 / 3,052 installed population, old readers on main)
- [x] Feed list (01b's profiling inventory never listed feeds without a reader, so it is built here from the code and the local disk; plan decision 38). No `edgar-warehouse` capture command remains; a captured feed is one the old pipeline wrote to bronze. 2026-10-09 09:08 ET

  | Feed | Configured reader | Local copy | Ticket 07 part |
  |---|---|---|---|
  | SEC submissions (Company, Person) | yes (`rules/sources/sec.submissions.*`) | yes (`clean-mdm/captures`, the proof slice) | none |
  | GLEIF Level 1, relationships, reporting exceptions | yes (`rules/sources/gleif`) | yes | none |
  | 13F information tables | yes (`rules/pipelines/sec-13f-reading`, bundle-tested) | 999 documents, 1.4 GB (`heavy-parse-13f`), 16 in the proof slice | none for the reader; silver onboarding (ticket 06 writer) |
  | Form ADV Part 1A, with Schedule D (custody 5.K(3), private funds, offices) | none (old parser deleted) | none | reader, then profiling |
  | Forms 3, 4, 5 (insider ownership XML) | none (old parser deleted) | none | reader, then profiling |
  | XBRL company facts | none | none | reader, then profiling |
  | 8-K and DEF 14A per-filing data | none | none | reader, then profiling (HTML parts: 07c) |
  | Investment adviser firm roster | none | none | reader, then profiling |
  | Filing text (HTML, iXBRL) | none | none | ticket 07c |

- [x] Local copies of the feeds with no reader, cut to the proof's cohort (plan decision 29: "every other captured feed sliced to one coherent cohort"; zero sec.gov requests; profiling never reads prod S3): none exists on this machine. Operator ruling, 2026-10-09 09:10 ET: "Read-only prod bronze slice (Recommended)": one read-only copy from prod bronze S3 (no writes, no prod changes) of these feeds for the proof's 500-entity cohort over 2 years, into the local proving folder with each file's sha256; size and time stated before the copy. Done 2026-10-09 09:48 ET: listing the cohort's 500 CIKs took 20 minutes (266 have filings in bronze); 25,246 objects, 2.71 GB, copied in 7 minutes by `trials/readers/copy_bronze.py` (GET only, 0 failed) into `~/.local/share/edgartools/clean-mdm/proving/p07/inputs/`, with `COPY.json` naming each key, size and sha256: the cohort's filings dated 2024-07-01 to 2026-06-30 (5,991 accessions; proxy statements 1.9 GB, 8-K 0.4 GB, 13F 0.2 GB, Forms 3 and 4), the whole `filing_artifact` folder (5,356 ownership documents, 109 MB) and the whole ADV bulk (13 monthly files, June 2025 to June 2026, 116 MB). A first try with one `aws s3 cp` per object ran at half a file a second and was stopped. Not in bronze, so not copied: XBRL company facts and the adviser firm roster (never captured)
- [x] Custody profiled (June 2026, ADV bulk; `trials/readers/custody-2026-06/`): the custody table is `IA_Schedule_D_5K3` (registered advisers only; exempt reporting advisers file no 5.K(3)), 3,022 rows, one per adviser filing and custodian: (a) legal name, (b) business name, (c) city, state, country, (d) related person, (e) SEC broker-dealer registration number (`8-…`, 73% filled), (f) another identifier (12% filled; 335 of 374 are LEIs), (g) amount held. Every row's filing is in `IA_ADV_Base_A` (inclusion 1.0), the master part (key FilingID); `IA_1D3_CIK` links filings to CIKs. 464 rows (15%) carry neither identifier, only names. Profiling classed custody "unknown" with no natural key: custodians appear only inside each row, so it cannot see a custodian master; the relationship is the operator's reading below 2026-10-09 09:52 ET
- [ ] Profiling gaps found here (Claude's skill): a zip of CSV files is refused ("one part holds JSON, JSON Lines or XML records"); DuckDB cannot sniff `IA_Schedule_D_7B1A25` (an irregular CSV), which stops the whole run; worked around by unzipping and profiling the three custody tables
- [ ] Custody items (operator, 2026-10-05: "Custody items are from Form ADV Schedule D 5.K(3)"): the source of custody data is Form ADV Part 1A, Schedule D, Section 5.K.(3), the custodians that hold separately managed account assets. Read it as its own part of the ADV feed: one row per adviser filing and custodian, with the custodian's name, identifiers and amount held. Profile it with data-profiling first. It is expected to be a relationship (adviser to custodian, both masters) with an amount, not a free-standing "Custody" disclosure category.
- [ ] For each feed whose records carry no id another source shares (for example custodians named only by name), map the name to the `name_id` cross-reference (`name_id@1`, ticket 07b) after `match_names.py` shows how it pairs; never where an id exists (added 2026-10-06 20:17 ET)
