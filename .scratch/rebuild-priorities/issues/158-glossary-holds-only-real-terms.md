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

- No `shared` glossary (operator, 2026-11-01: "i dont want any shared"; "use the CONTEXT section names"). A relationship type goes in the glossary of the domain its `from` list names first; other terms go in a glossary named after their `CONTEXT.md` section.
- Not glossary terms: `Discretion` (a silver field, `discretion_type`) and `Holdings` (silver rows). `Governed Role Profile` was an umbrella word added in PR #657 (2026-09-19) before any real profile existed; the `profiles` key in the source-contract spec used it. `Market/Venue` is real: the ISO 10383 MIC code set in RDM and the OpenFIGI listing rules; it was removed by mistake and restored.

## Parts

- [x] Both market terms removed from `shared` (hard delete through the API): 47 terms before, 45 after, neither name listed (2026-11-01 18:41 ET)
- [x] `skills/openmetadata/SKILL.md`, "Glossary and classification": publish a term only when real data backs it; a planned type is not published; no domain or glossary for planned terms; a type of one domain goes in that domain's glossary, not `shared` (2026-11-01 18:41 ET)
- [x] Four more terms removed from `shared` and `IS_SUBFUND_OF` kept; 47 terms at the start, 41 now (2026-11-01 19:04 ET)
- [x] `CONTEXT.md` "Audit Firm Profile" renamed "Audit Firm"; the skill says a kind of an identity is named by the kind and goes in its domain's glossary (2026-11-01 19:04 ET)
- [x] More terms removed ("yes, remove it" / by the same ruling): `AUDITED_BY` (no rule, no link), `INVESTMENT_ADVISER_TO` (adviser can be a person or a company: 6 of 2,409 filings in the October 2025 Form ADV capture are sole proprietorships; but no rule creates the link). `CUSTODIAN` kept (rules read it). 39 terms in `shared` (2026-11-01 19:16 ET)
- [x] The 8 planned types stay as `mdm.relationships` assets, each description ending "(planned: no rule reads this type yet and no link is loaded)": written by hand in the local catalog; asset versions 1.4 to 1.5, certification unchanged (2026-11-01 19:16 ET)
- [ ] ~~Make the planned marker permanent in `catalog.py`~~ deferred to ticket 159: the publisher still writes `shared`, so one code change covers both
- [x] `Governed Role Profile` deleted from the glossary, from `CONTEXT.md` and from the spec; `Adviser Profile` and `Fund Profile` renamed `Adviser` and `Fund` in `CONTEXT.md` (2026-11-01 19:35 ET)
- [x] `CUSTODIAN` moved to the `company` glossary, with `Audit Firm`, `Adviser`, `Fund` and `Fund Company`; `Fund Series` to `fund_structure` (2026-11-01 19:35 ET)
- [x] The terms walked one by one with the operator, each kept, moved or removed: the local glossary now has 11 terms in `company`, 19 in `mdm_identities_and_mastering`, 3 in `data_classes_reference_data_and_agent_context`, 3 in `security`, 2 each in `person` and `fund_structure`, 1 each in `branch`, `government` and `international_organization`, 1 in `market_venue`; `shared` deleted (2026-11-01 19:35 ET)
- [ ] The Approved status: all 47 were Approved, the skill says "do not mark a term approved"; decide and fix (operator)
- [x] `Market/Venue` restored in the `market_venue` glossary (2026-11-01 19:35 ET). The definition still names the two removed link types: reword it (open)
- [ ] Silver definitions: `discretion_type` and the holdings rows get their definition on the silver column or table (no silver table for the 13F holdings is in the catalog yet)
- [x] Learning → skill: `skills/openmetadata/SKILL.md`, "Glossary and classification": no `shared`; placement by kind; silver data and umbrella words are not terms; a domain is tested by its own data (2026-11-01 19:35 ET)
