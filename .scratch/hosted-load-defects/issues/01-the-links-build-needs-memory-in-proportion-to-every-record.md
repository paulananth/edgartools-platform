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

- [ ] GoF consult on `edgar_warehouse/mastering/links.py`, `mdm/relationships.py` and the Rust `prepare_relationships`
      (CLAUDE.md, Code review): where the seam is (stream the records in, or split by independent groups)
- [ ] Decide the bound (the loader container's memory, 3.9 GB, is what a hosted finish must fit) and how a link that several
      records state (evidence and periods across records) stays one link when the records are read in parts
- [ ] Test first: a store whose records state the same link from two sources, built whole and built in parts, gives the same
      links, evidence and periods
- [ ] Implement; the Rust change gets the `risky-reviewer` agent (CLAUDE.md, Code review)
- [ ] Measure on the hosted store: peak memory under the container's limit, and the finish within its five-minute bound
- [ ] Learning → skill: `data-operations/HOSTED-LOADS.md`, "The finish takes at most five minutes": the finish's memory is
      about 15 times its record text, and a container smaller than that kills it with status -9
