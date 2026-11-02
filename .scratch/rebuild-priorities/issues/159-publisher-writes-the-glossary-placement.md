# 159: The catalog publisher follows the glossary placement rules

Priority: 159. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 19:35 ET, from ticket 158 (operator, 2026-11-01).

Type: task. Status: open. Blocked by: none.

## Question

`edgar_warehouse/rules/catalog.py` (lines 475 to 557) still creates a `shared` glossary and puts the type terms in it. The next
catalog publish would undo the placement the operator ruled in ticket 158. Can the publisher write what the skill now says?

## Parts

- [ ] A test states the placement: a relationship type in the glossary of the domain its `from` list names first; other terms in a glossary named after their `CONTEXT.md` section; no `shared` glossary
- [ ] A test states the planned marker: a type no file under `rules/sources/` reads gets "(planned: no rule reads this type yet and no link is loaded)" in its asset description, and no glossary term
- [ ] A test states the data classes: a `data_class` tag on each table (master data on a kind table, reference data on a code-set table, relationship on a relationship-type table, transaction data on a prepared-store table), the `Reference Hierarchy` text in the code-set descriptions, and the relationship capacity and dated interval text in the relationship-type descriptions
- [ ] A test states that no glossary is made for a `CONTEXT.md` section and that a platform word is not published
- [ ] A test states that an entry describing silver data (`Discretion`, `Holdings`) and a name ending in "Profile" are not published as terms
- [ ] `catalog.py` writes them; the three review axes; PR
- [ ] Learning → skill: none expected (ticket 158 holds the rules)
