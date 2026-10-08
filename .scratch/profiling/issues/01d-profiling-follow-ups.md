# 01d Profiling follow-ups (deferred parts of 01b and 01c)

Type: task. Phase: A. Blocked by: 01b, 01c. Map: [map](../map.md). Plan: [plan](../plan.md).

The deferred parts of 01b and 01c that can be done locally now (operator,
2026-10-08: "Yes", after the list of what can be worked on). One PR each.
Still blocked and left on their tickets: Snowflake in place (no non-prod
Snowflake; profiling never reads prod), the placeholder EIN, `TYPES_V0`, roles on
real data, approvals in a Rules Database.

## Checklist

- [x] Distribution drift in compare: each column's distribution in findings.yaml (quantiles of a number or date, shares of a code's values; none for personal columns); compare reports PSI for codes and KS for numbers and dates (01b line 24): `profile.distribution`, `drift.distribution_drift`, `psi`, `ks`; GoF consult: one more section in `compare` and two small measures, Rule 0; chi-square left out (on a large delivery any difference is significant); tests: distributions kept and never for a personal column, a tripled amount and a moved group reported, PSI and KS values (135 profiling tests pass); findings spec §2 and §7, SKILL.md compare 2026-10-08 11:02 ET
- [x] Drift review (Standards, Spec, GoF): GoF leave it; fixed: a long code list no longer drifts when values only swap out of the listed top 200 (a value missing from an incomplete list joins "other"), a zoned time is its own instant, a column whose measure changed kind is reported, infinite values left out of quantiles, KS exact at a jump, the thresholds' source stated correctly (138 profiling tests pass) 2026-10-08 11:05 ET
- [ ] Drift: PR, CI, merge on the operator's word
- [ ] Coincidental dependencies told from real hierarchies (01c line 20)
- [ ] Evidence from separate level tables, tested on a data set that has them (01b line 22)
- [ ] Snapshot-or-changes, versions per key, refresh rate and key persistence from two deliveries, on fixtures (01b line 27); a real-data result needs a second delivery of a local feed
- [ ] A hierarchy check in the engine (01c line 21): new code; using it in a live quality.yaml is a rule version for the operator's approval
- [x] Ticket 05b: its PR, CI and merge part checked (#868, 1539704d) 2026-10-08 11:00 ET
