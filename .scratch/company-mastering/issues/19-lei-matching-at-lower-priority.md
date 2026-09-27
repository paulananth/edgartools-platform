# Investigate matching on an LEI below the name rules

Type: research
Status: resolved (2026-09-26 20:00 ET); a decision is waiting on the operator
Blocked by: none

## Question

Operator, 2026-09-26: "investigate using lei for matching in lower priority".
Could an LEI join an SEC Company to its GLEIF record when the name rules do
not? Two claims are measured:
- SEC's own `lei` field;
- GLEIF's record naming the CIK under registration authority `RA000665`.

What would such a rule add, can it be proven, and how would it sit below the
name rules?

## Checklist (times ET)

- [x] Read ticket 08's measurement of SEC's LEI and of `RA000665`
  (2026-09-26 19:55 ET).
- [x] Pin the inputs: `cm08-coverage-2.jsonl` (`97e5d118…`, the file
  `08-parity.json` pins) and the two local GLEIF extracts (19:58 ET).
- [x] Split each claim into three groups: agrees with the name rules,
  conflicts, or reaches a Company the name rules miss. Look up each extra
  one in GLEIF (20:00 ET).
- [x] The bar (`company-policy.md`: confidence bands and Q14) and the engine's
  order (`matching.propose`) (20:00 ET).
- [x] Write it up: [research 19](../research/19-lei-matching-at-lower-priority.md)
  (20:00 ET).

## Answer

- **SEC's own LEI.** 10 of 6,414 Companies state one and 7 are valid:
  - 3 agree with the name rules;
  - 0 conflict;
  - 4 reach Companies the name rules miss, and all 4 look right when read by
    hand.
- **GLEIF naming the CIK (`RA000665`).** 10 Companies:
  - 6 agree;
  - 0 conflict;
  - the 4 extra targets are poor: one DUPLICATE record, two FUND records and
    one LAPSED record with a jurisdiction conflict.
- **The bar.**
  - Neither claim qualifies for Q14's proof-free identifier path, because SEC
    does not issue LEIs.
  - Each needs the 95% measured bar. That takes at least 52 correct pairs,
    and today's data has 7 and 10.
- **In the engine.** A lower-priority rule would run after the name rules, on
  GLEIF records that are still unbound. It would read SEC's LEI as a matching
  value, never as the `lei` identifier. The loader has to carry SEC's LEI
  first.

**Recommended, not decided:**
- do not build the rule now;
- keep SEC's LEI lookup-only, and also store it as a matching value so a
  conflict check can flag disagreement;
- reach the 4 missed Companies by improving the name rules;
- look again when the Fund kind starts.
