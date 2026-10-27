# 139: N-PORT holdings filed with only a FIGI find their Security

Priority: 139. Map: [Rebuild priorities](../map.md). Opened 2026-10-27 16:50 ET.

Type: task. Status: open, not started.
Blocked by: none. Comes from [138](138-one-security-mastering-by-cross-reference.md)'s
N-PORT FIGI line (operator, 2026-10-27: "Drop the rule, new ticket (Recommended)").

## Why

N-PORT files a FIGI in `OTHER_IDENTIFIER` (descriptions such as "FIGI",
"BBGID", "Bloomberg identifier"). Measured on 2026 Q2, counts only (ticket 138):

- 16,600 holdings file a valid FIGI. Only 508 of them also carry a CUSIP or an
  ISIN, so only those make an N-PORT Security record today. Of the 508, 479 already
  sit on the Security holding their FIGI, 27 file a FIGI no OpenFIGI Security
  holds, 1 would join through it and 1 conflicts (its CUSIP wins). A FIGI rule
  on today's records changes 1 record, so 138 dropped it.
- 16,092 holdings file only a FIGI (6,026 distinct, one per holding). They make
  no Security record, so their holdings point at no Security. 1,106 of them
  (123 FIGIs) carry a FIGI an OpenFIGI Security holds.

## Parts

- [ ] Decide the record: an N-PORT Security record keyed by its FIGI when the
  holding carries no CUSIP or ISIN, the FIGI a cross-reference (N-PORT does not
  issue FIGIs; it finds and never creates or merges, Design 5); the rest wait
- [ ] Decide whether to ask OpenFIGI by FIGI for the 5,903 FIGIs no Security
  holds (a new provider request: needs the operator's permission first)
- [ ] Source extract, Dataset Contract and a lookup-only rule, off until a
  limited test and the operator's switch-on
- [ ] The silver holding row takes the Security its FIGI finds
- [ ] Tests, three-axis review, PR, CI green, merge
- [ ] Learning → skill
