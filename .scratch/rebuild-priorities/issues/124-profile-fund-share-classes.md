# 124: Profile fund share classes

Priority: 124 (operator, 2026-10-20: "Do we need to resolve and store share
classes", then, asked which: "A fund's share classes", and "Profile first
(Recommended)"). Map: [Rebuild priorities](../map.md).

Type: task. Status: resolved (2026-11-04 06:44 ET): profiled; the operator ruled not to master the classes now. Blocked by: none.

## What is known (2026-10-20, measured on the captured 2026 Q2 N-PORT data set)

- A fund's share classes (Class A, Class I, ...) sit under a fund series.
  MDM holds Funds (`sec.nport.fund`) but no share classes.
- The N-PORT data set names a class in one table only: `MONTHLY_TOTAL_RETURN`
  (`CLASS_ID` with three monthly returns): 31,640 rows, 29,407 distinct class
  ids of one shape (`C` and nine digits) over 13,824 filings; 854 rows have no
  class id.
- N-PORT gives no class name and no ticker. Those are in the SEC's series and
  class list, which is not captured. Capturing it is a provider request: ask
  the operator first.

## Checklist

- [x] Profile the class data in the captured N-PORT data set, counts from the 2026 Q2 file (2026-11-04 06:38 ET): 31,640 class rows; 29,407 distinct class ids, every one `C` and nine digits; 854 rows carry no class id. 29,406 classes sit under one series, 1 under two. 12,944 series have classes (median 1 class, most 25; 7,159 series have exactly 1). 28,293 classes (96%) appear in one filing only, so a class seen over time needs more than one data set. A class row holds three monthly returns and nothing else
- [x] What a class record would hold (2026-11-04 06:38 ET): without the SEC's series and class list, the class id, its series (the Fund it belongs to), and the monthly returns by filing; no name, no ticker. The list would add the class name and ticker (and so the link from a Form 4 or OpenFIGI ticker to a fund class), at the cost of a provider request that needs the operator's permission
- [x] Findings and the one question brought to the operator (2026-11-04 06:44 ET): master the classes under the fund series? Answer "No, not now (Recommended)": a class has no name or ticker without the SEC series and class list (a provider request that needs permission), so mastering would add 29,407 records holding only returns; revisit when that list is captured
- [x] Learning → skill: none (2026-11-04 06:44 ET); the ruling is recorded here
