# Guide for Summarize every row

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `docs/rules-try/whole_set.md` only. Words, stored keys, the three-row case, and the tie. Do not edit another guide. No test.

## Checklist

- [x] `docs/rules-try/whole_set.md` is the only file this ticket adds, besides this ticket file and the map line. 2026-11-25 21:56 ET
- [x] The guide has the three-row case and the tie. The outputs are what `whole_set` returned when run on the invented rows. 2026-11-25 21:56 ET
- [x] Learning → skill: none. The guide records the output of tickets 10 and 11. 2026-11-25 21:56 ET

## Answer

`docs/rules-try/whole_set.md` lists the three words (how many rows, distinct values, most frequent) beside their stored modes (`count`, `members`, `most`), says where they go, and names the refusals (a bare stored mode, "how many at this path"). It carries the invented three-row case (`Alpha`, `Beta`, `Alpha` under `K1`): the short rule, the lines Show the full rule prints, the rows, and what Try returns (a count of 3, two distinct values, `Alpha` most frequent). The tie (`Alpha`, `Beta`) returns a blank most frequent value. No test.

## Comments

