# 08 Recreation proof

Type: task. Phase: B. Blocked by: all above. Map: [map](../map.md). Plan: [plan](../plan.md).

## Ruling (operator, 2026-10-07)

Only SEC submissions, the GLEIF Golden Copy and 999 13F information tables are
on this machine; every other feed is only in production bronze, which the plan
says profiling never reads. The operator: "Local feeds only (Recommended)": the
cohort is fixed from local feeds; the proof covers those and the 13F tables on
hand, and DIFF.md lists every other feed as not covered. No production read.

## Checklist

- [x] Cohort list (500 entities, 2 years) in the repo, with size and time (`.scratch/profiling/trials/cohort/`: `cohort.json`, `select.py`, README with the strata, size and time): 4 named, 171 bound to GLEIF, 75 held for a steward (all 8 reasons), 75 with no GLEIF record, 75 investment, 100 other filers; 222 with an LEI; 46 MB of SEC submissions 2026-10-07 19:57 ET
- [ ] Rulings file replayed in sandbox
- [ ] Cold agent regenerates into sandbox stores
- [ ] DIFF.md: every line matched or explained
- [ ] Operator accepts — program ends
