# 162: A fund is a collection of securities, not a company

Priority: 162. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 21:02 ET, from the glossary review (operator, 2026-11-01: "fund is not a company, fund is collection of securities").

Type: task. Status: resolved. Blocked by: none.

## Question

The term Fund sat in the company glossary and `CONTEXT.md` defined it as the fund registration of a Company or a Fund Structure. Which glossary holds it, and what does it say?

## Parts

- [x] `CONTEXT.md` defines Fund as a collection of Securities that pools investors' money, not a Company; a Fund Structure is a fund that is no company, and a Company can also hold a governed fund registration (2026-11-01 21:02 ET)
- [x] The publisher places Fund in the fund_structure glossary; Fund Company (the SEC registrant) stays in company (`tests/unit/test_rules_catalog.py::test_only_entity_terms_are_published_as_draft_terms`, 2026-11-01 21:02 ET)
- [x] Live: the term moved to `fund_structure.Fund` with `moveAsync`, the publish updated its text, `check` matched, 22 of 22 terms Draft (2026-11-01 21:02 ET)
- [ ] ~~The publisher deletes a term the plan no longer names~~ deferred: a moved term needs the API move by hand until it does; open a ticket if terms move again
- [x] Learning → skill: none (ticket 158 holds the placement rules; the move is one entry in the code's kind table)
