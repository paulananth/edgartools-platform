# Rewrite SEC-to-GLEIF matching as priority name-and-address passes

Type: research, then build
Status: in progress
Blocked by: none

## Question

Operator, 2026-09-27: "re write the matching logic using priority, name and
address first, it it matches merge it, no need to match on jurisdiction
/research how to impliment priority mergeing, you merge with all fields first
then you reduce the fields gradually until you get more mergeing".

This replaces the two jurisdiction and postcode rules of ticket 08, and the
"/DE" and Wilmington fixes the operator asked for earlier the same day
(ruling: a Wilmington seat binds only when SEC agrees or is silent).

## Checklist (times ET)

- [x] Research note on cascade matching started (2026-09-27 19:50 ET):
  [research 21](../research/21-priority-matching.md).
- [x] Measure a pass ladder on the ticket 08 inputs (20:00 ET):
  [`21-tiers.py`](../research/21-tiers.py), result
  [`21-tiers.json`](../research/21-tiers.json).
- [ ] Read the research note; settle the pass ladder and its safeguards.
- [ ] Put the result and the one open question (below) to the operator.
- [ ] Label a sample per pass; prove each pass at the 95% bar.
- [ ] `/gof-refactor-reviewer`, then build the passes as rules data.
- [ ] Three-axis review, PR, CI; merge on the operator's word.

## Measured (2026-09-27 20:00 ET)

Inputs: `cm08-coverage-2.jsonl` (`97e5d118…`, the 6,414 Companies), all
76,230 SEC filers (`cm08-sec-scan.jsonl`) and all 3,428,477 GLEIF records of
the 2026-09-11 16:00 UTC Golden Copy (`cm08-gleif-all.jsonl`).

Each pass takes only what is still unmatched and binds a pair only one to
one. Names are equal with the legal form kept, counting GLEIF's other names.
The GLEIF entity is GENERAL, ACTIVE, not DUPLICATE or ANNULLED. A registered
agent's address gives only its country.

| Pass | Companies bound |
|---|---:|
| P1 name + street + city + postcode | 1,463 |
| P2 name + street + postcode | 90 |
| P3 name + street + city | 109 |
| P4 name + postcode | 424 |
| P5 name + city | 281 |
| P6 name + country | 1,036 |
| P7 name alone | 181 |
| **All passes** | **3,584** |

Today's two rules bind 3,050. The passes keep 3,048 of them, with the same
LEI, and add 536: 456 that wait today, and 80 that today find no GLEIF
record, through GLEIF's other names (Canon, Hitachi, Sony, Nokia).

## Open

- **AAON, Inc.** passes P1, and is wrong: GLEIF's AAON is the Oklahoma
  subsidiary of SEC's Nevada parent, at the same address. Only jurisdiction
  told them apart. Ticket 08's labels also hold 23 "unresolved" pairs the
  passes would bind, each with SEC and GLEIF naming different states (Hyatt:
  SEC Illinois, GLEIF Delaware).
- P5 to P7 have few labelled pairs (49, 181, 66), all drawn from today's
  binds; each pass needs its own draw.
