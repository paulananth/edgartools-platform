# Rewrite SEC-to-GLEIF matching as priority name-and-address passes

Type: research, then build
Status: in progress
Blocked by: nothing. Ticket 22 (data quality) merged 2026-09-28 09:50 ET (#742).

Operator ruling, 2026-09-27, after the research and three measured designs:
"need data quality checks before merge, dq will be a seperate rule, finally
cascade merge". So this ticket builds the operator's cascade, on the values
ticket 22's quality rule leaves fit to use.

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

## Decided: a conflict in place of incorporation (operator, 2026-09-28 19:49 ET)

Asked whether a pass should refuse a pair when SEC's state of incorporation
and GLEIF's jurisdiction differ (the AAON case), the operator answered "They
both may be true Hyatt (SEC says Illinois, GLEIF says Delaware)". GLEIF's
Hyatt Hotels Corporation (T27JQIMTYSH41TCD5186) is US-DE, so SEC's Illinois
is likely stale: the same company. GLEIF's only "AAON, INC."
(549300ZHF0E5VM7PUD37) is US-OK, and ticket 08's labels found it the
subsidiary: nothing in the pair itself tells the two cases apart.

Ruling ("Yes" to the recommendation): **no veto; the proof decides.** A pair
whose places of incorporation conflict goes through the passes like any
other and is its own labelled stratum. If that stratum clears the 95% bar
it binds; if not, those pairs go to a Steward for review.

## Decided: the approved rules stay until ticket 20 (operator, 2026-09-28 20:27 ET)

The two matching rules in use (Name-and-state, Postcode) carry the approved
fingerprint `983352e8…4049`. Asked whether this ticket may leave them in
place, the passes added switched off, the operator answered "Yes". Ticket 20
swaps them in one step, on the passes' proof and a new approval.

Design (advisor review, 2026-09-28): the cascade is decided once, over both
whole sources, by one production function a new Name Census version carries
per CIK (the LEI, its pass, its flags); the Merge Stage re-checks the pair
on its own rows. The proof calls the same function, so it measures what runs.

## Decided with ticket 22 (operator, 2026-09-28)

- **Addresses:** a pass compares the address the quality rule left fit:
  GLEIF's headquarters address first (`matching.headquarters_address`),
  else its legal address (`matching.address`); SEC's business address
  (`matching.address`). A withheld address is never compared.
- **Over-shared address threshold: 25** ("25, yes", 09:50 ET). An address
  (standardized street, 5-digit postcode, country) that more than 25
  entities use is not compared by any pass: 3,604 addresses, 271,352 GLEIF
  entities, on the ticket 08 inputs
  ([ticket 22 proof](../research/22-quality-proving-run.json)). It is a
  check across records, so it sits with the Company merge rules.
