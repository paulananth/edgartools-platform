# 03: Form ADV private-fund reading gaps the spec reviews found

Type: task
Status: open
Blocked by: none
Blocks: none
Labels: wayfinder:task

Found by the two spec reviews of ticket 01 (2026-11-24); the hosted reload ran with them open, each measured as small.
Moved here from ticket 01 so that ticket closes with the hosted load.

## Checklist

- [ ] The 7.B readings carry no section or filing-action field (the reading a row comes from is its section).
- [ ] Two advisers reporting one PFID with different master funds: the latest filing's row decides the feeder link (March: 3 of 2,714 IA feeders and 1 of 358 ERA feeders name two masters, each across filings; June none). A test and a rule for it.
- [ ] The "latest" 7.B(1) row orders FilingID as text (seven digits on every row of March and June); order it as a number.
- [ ] An ERA filing with an 801- number is left out by `select` with no set-aside reason (20 in March, 90 in June, each present in the IA file too): give it a reason; later months are not checked.
- [ ] `distinct_on` keeps one row of a filing and fund without reporting a conflict, and no test covers conflicting duplicate rows.
- [ ] Same-month contradictory roles (4, of two advisers: one filing stating both roles for one fund) drop the link: say which role wins.
- [ ] Learning → skill: none until a rule changes.
