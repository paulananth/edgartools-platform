# 04: The links build reads every record whole to use its links

Status: open
Type: bug
Blocked by: none
Blocks: the finish within its five-minute bound (ticket 01)

Found 2026-11-25: the finish after the bounded-memory fix took 6.1 minutes against the five-minute bound (landing
included). Measured phase by phase inside the loader container (460 s with the timing wrapper, one run): read the
records 136 s (30%), land the four tables 160 s (35%), bind the ends 31 s, read the masters 24 s, calculate 24 s, bind
`master_binding` 25 s, fold 9 s, the rest 20 s. The build reads 504,359 records, 896 MB of text, to use 230 MB of it
(each record's identity and its links); the profiles, fields and identifiers are never read.

## Checklist

- [x] Operator, 2026-11-25: "can this not be done in the database itself 7 wastes", then "yes make the read cut and open the PR" (2026-11-25 11:15 ET)
- [x] Measured on the hosted store, read only: the whole bodies 896 MB in 127 s; the links cut in the database 230 MB in 66 s (2026-11-25 11:15 ET)
- [x] The PostgreSQL query sends the identity, the revision keys and the links of each record, and an empty stand-in for the fields, identifiers and profiles the reader requires; `json` keeps the links' text as stored (2026-11-25 11:15 ET)
- [x] Test first: `test_the_links_build_reads_the_same_links_from_the_cut_records_as_from_whole_ones`; with the whole body in place of the cut it fails on `assert (5722 < (5722 / 2))`; with the cut it passes, and the links calculated from both are equal (2026-11-25 11:15 ET)
- [x] The hosted store, read only: the rows calculated from the cut records and from the whole bodies are equal in every table (416,934 links, 478,867 evidence rows, 0 path rows, the same four waiting counts); the two reads ran 208 s and 218 s on this Mac, whose network is not the loader's (2026-11-25 11:15 ET)
- [ ] The finish's time read from the next hosted load, landing included
- [ ] MySQL reads whole bodies still: its cut is `json_object` over `json_extract`, a ticket of its own if MySQL is ever a hosted store
- [ ] Landing is 35% of the finish (160 s, about 1.3 million rows to the hosted store); whether its time is round trips or volume is not yet measured
- [ ] Learning → skill: none
