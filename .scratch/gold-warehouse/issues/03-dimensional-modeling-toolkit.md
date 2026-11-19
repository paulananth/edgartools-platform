# Dimensional modeling toolkit in the data-modeling skill

Status: open
Type: task

The operator asked to update the skills with dimensional modeling intelligence. The technique list is the Kimball Group's
published list of dimensional modeling techniques (read from the Kimball Group's page, which names the techniques and does
not define them); the definitions and their mapping to this platform are mine and unreviewed.

## Parts

- [x] Read the technique list from its primary source and map each technique to what MDM, RDM and silver already hold. 2026-11-19 08:52 ET
- [x] Write `skills/data-modeling/DIMENSIONAL.md` (four steps, bus matrix, fact and dimension types, additivity, keys, history types, missing and late keys, drilling across, proofs, smells) and link it from `GOLD.md`, `SKILL.md` and `semantic-views`. 2026-11-19 08:52 ET
- [x] Genericity, no-ticket, guide-path and skill-length tests: 149 passed (one fix: source words moved out of the generic text). 2026-11-19 08:52 ET
- [ ] Operator reviews the platform rulings it proposes: dimension attributes stay null in the data (labels are the semantic layer's); type 1 is the default and type 2 only on a named requirement; a ratio is stored as its parts
- [ ] Learning → skill: `DIMENSIONAL.md` itself; gaps found when the first slice is built return here
