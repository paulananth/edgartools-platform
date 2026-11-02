# 159: The catalog publisher follows the glossary placement rules

Priority: 159. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 19:35 ET, from ticket 158 (operator, 2026-11-01).

Type: task. Status: in progress. Blocked by: none.

## Question

`edgar_warehouse/rules/catalog.py` (lines 475 to 557) still creates a `shared` glossary and puts the type terms in it. The next
catalog publish would undo the placement the operator ruled in ticket 158. Can the publisher write what the skill now says?

## Parts

- [x] A test states the placement: a relationship type in the glossary of the domain its `from` list names first; other terms in a glossary named after their `CONTEXT.md` section; no `shared` glossary (tests/unit/test_rules_catalog.py::test_a_relationship_type_is_a_term_of_the_domain_its_from_list_names_first, 2026-11-01 20:11 ET)
- [x] A test states the planned marker: a type no file under `rules/sources/` reads gets "(planned: no rule reads this type yet and no link is loaded)" in its asset description, and no glossary term (test_a_type_no_rule_reads_stays_an_asset_marked_planned, 2026-11-01 20:11 ET)
- [x] A test states the data classes: a `data_class` tag on each table (master data on a kind table, reference data on a code-set table, relationship on a relationship-type table, transaction data on a prepared-store table), the `Reference Hierarchy` text in the code-set descriptions, and the relationship capacity and dated interval text in the relationship-type descriptions (test_each_table_carries_its_data_class, 2026-11-01 20:11 ET)
- [x] A test states the data products: each carries its domain and its "<Domain> Identity" glossary tag in the `Suggested` state (the publisher writes products without tags today) (test_each_data_product_carries_its_identity_term_in_the_suggested_state, 2026-11-01 20:11 ET)
- [x] A test states that a glossary term is written as Draft, never Approved (the skill: do not mark a term approved) (test_a_term_is_written_as_draft_never_approved, 2026-11-01 20:11 ET)
- [x] A test states that no glossary is made for a `CONTEXT.md` section and that a platform word is not published (test_only_entity_terms_are_published_as_draft_terms, 2026-11-01 20:11 ET)
- [x] A test states that an entry describing silver data (`Discretion`, `Holdings`) and a name ending in "Profile" are not published as terms (test_only_entity_terms_are_published_as_draft_terms, 2026-11-01 20:11 ET)
- [x] `catalog.py` writes them (29 catalog tests pass, plan = the 22 live terms, 2026-11-01 20:11 ET); the three review axes; PR
- [ ] Learning → skill: none expected (ticket 158 holds the rules)
