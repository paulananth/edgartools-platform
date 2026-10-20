# 124: Profile fund share classes

Priority: 124 (operator, 2026-10-20: "Do we need to resolve and store share
classes", then, asked which: "A fund's share classes", and "Profile first
(Recommended)"). Map: [Rebuild priorities](../map.md).

Type: task. Status: open. Blocked by: none.

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

- [ ] Profile the class data in the captured N-PORT data set (data-profiling skill, one run): class id to series, to filing, returns
- [ ] Say what a class record would hold without the SEC's series and class list, and what that list would add
- [ ] Bring the findings and one question (master the classes under the fund series, or not) to the operator
- [ ] Learning → skill
