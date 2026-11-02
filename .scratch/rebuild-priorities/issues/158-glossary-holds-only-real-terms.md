# 158: The glossary holds only terms that real data backs

Priority: 158. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 18:41 ET, from reading the `shared` glossary term by term
(operator, 2026-11-01: "list one by one, get feedback and adjust the skill").

Type: task. Status: in progress (Claude, branch `claude/t158-glossary-real-terms`). Blocked by: none.

## Question

The local OpenMetadata `shared` glossary held 47 terms, all written by the `admin` login through the API and all marked Approved.
Two of them (`HAS_MARKET_OPERATOR`, `IS_SEGMENT_OF_EXCHANGE`) name relationship types for data nobody has loaded, and
`CUSTODIAN` is a kind of Company. Which terms belong, and where?

## Rulings so far (operator, 2026-11-01)

- `CUSTODIAN`: "custodian is a type of company it is not shared, its a subdomain or subtype of company it must not show up in the shared domain".
- `HAS_MARKET_OPERATOR`, `IS_SEGMENT_OF_EXCHANGE`: "yes, remove both from the glossary, make sure it is documented and the skill must be intelligent, can not create fake domains". No rules file uses either; no market-code file is held.

- Walk so far, one term at a time: `IS_FEEDER_TO`, `IS_FUND-MANAGED_BY`, `IS_INTERNATIONAL_BRANCH_OF`, `IS_SUBSIDIARY_OF` removed ("yes, remove it"): no rules file uses the code, and the shared store holds no link of any type (checked 2026-11-01: 375,440 entities, 0 relationships). `IS_SUBFUND_OF` kept ("yes, keep it"): rules read it (GLEIF sub-fund pairs). `AUDITED_BY` and `CUSTODIAN`: Company types, not shared ("audited by is another company").
- `Audit Firm Profile` is `Audit Firm`, a type of company, not shared (operator, 2026-11-01).

## Parts

- [x] Both market terms removed from `shared` (hard delete through the API): 47 terms before, 45 after, neither name listed (2026-11-01 18:41 ET)
- [x] `skills/openmetadata/SKILL.md`, "Glossary and classification": publish a term only when real data backs it; a planned type is not published; no domain or glossary for planned terms; a type of one domain goes in that domain's glossary, not `shared` (2026-11-01 18:41 ET)
- [x] Four more terms removed from `shared` and `IS_SUBFUND_OF` kept; 47 terms at the start, 41 now (2026-11-01 19:04 ET)
- [x] `CONTEXT.md` "Audit Firm Profile" renamed "Audit Firm"; the skill says a kind of an identity is named by the kind and goes in its domain's glossary (2026-11-01 19:04 ET)
- [x] More terms removed ("yes, remove it" / by the same ruling): `AUDITED_BY` (no rule, no link), `INVESTMENT_ADVISER_TO` (adviser can be a person or a company: 6 of 2,409 filings in the October 2025 Form ADV capture are sole proprietorships; but no rule creates the link). `CUSTODIAN` kept (rules read it). 39 terms in `shared` (2026-11-01 19:16 ET)
- [x] The 8 planned types stay as `mdm.relationships` assets, each description ending "(planned: no rule reads this type yet and no link is loaded)": written by hand in the local catalog; asset versions 1.4 to 1.5, certification unchanged (2026-11-01 19:16 ET)
- [ ] Make the planned marker permanent: `catalog.py` writes it for any type no file under `rules/sources/` reads, with a test (a hand-written marker is overwritten by the next publish)
- [ ] `Audit Firm`, `CUSTODIAN`, `AUDITED_BY` (if kept) placed in the `company` glossary, and the sibling profile terms (Adviser, Fund, Governed Role) decided
- [ ] `CUSTODIAN` moved from `shared` to the `company` glossary
- [ ] The other 44 terms walked one by one with the operator, each kept, moved or removed
- [ ] The Approved status: all 47 were Approved, the skill says "do not mark a term approved"; decide and fix (operator)
- [ ] `Market/Venue`: in `shared` while the `market_venue` glossary has 0 terms (the heading has a slash, the display name a space); decide the home (operator)
- [ ] Learning → skill: `skills/openmetadata/SKILL.md`, the first two parts; add the rest as they are decided
