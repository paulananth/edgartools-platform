# 190: A Security's key is any identifier class, not CUSIP or ISIN only

Switch-on: standing approval (operator, 2026-11-04 07:00 ET: "switch on for form 4 keep it standing approval for ticket 190 191"): it is switched on once its limited test passes, with the counts recorded here and no question asked.

Priority: 190. Map: [Rebuild priorities](../map.md). Opened 2026-11-04 01:44 ET, from [ticket 125](125-securities-and-funds-uniquely-identifiable.md) (operator, 2026-11-03: "yes do option 1 and open the follow-up ticket").

Type: task. Status: approved to build (operator, 2026-11-04 06:46 ET: "approve 190 and 191"). Blocked by: [125](125-securities-and-funds-uniquely-identifiable.md) (its SEDOL and LoanX join slice, which this follows).

## Question

Ticket 125 lets a SEDOL or a LoanX **join** the Security a holding already keys by its CUSIP or ISIN. It does not let one **create** a Security when a holding carries neither a CUSIP nor an ISIN: the engine reads the key class from three places that each know only CUSIP and ISIN, so adding a class copies about six files (the source's key tables, the reduction groups, the combination, the Identifier Contracts, the verification test and the mapping documents).

Make the key class a configured list (each class with its Identifier type, its table and its label), so that adding the third class is a rules change and one test, and a Security with only a SEDOL or a LoanX is created.

## Parts

- [ ] Count first (counts only): how many 2026 Q2 holdings carry a SEDOL or a LoanX and no CUSIP or ISIN, and how many distinct Securities that would add
- [ ] GoF consult on the key-class code in the N-PORT Security chain
- [ ] The key classes declared once in the source's rules; the chain reads the list
- [ ] A SEDOL-only holding creates one Security; a second holding with the same SEDOL joins it; a holding with a CUSIP and a SEDOL keeps its CUSIP key (tests on invented data, one per case)
- [ ] The Identifier Contracts verified on a test run (no identifier on two Securities); approved under the standing approval
- [ ] Mapping documents regenerated; the whole CI set
- [ ] PR, CI green, merged on green
- [ ] Learning → skill (`security-master`; `data-onboarding`, the gaps table)
