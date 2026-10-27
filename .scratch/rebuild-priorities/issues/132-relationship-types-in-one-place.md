# 132: Relationship types in one place

Priority: 132, tier 2. Map: [Rebuild priorities](../map.md). Opened 2026-10-22
from a lean review of how MDM masters relationships (operator: "Is this
following lean principles especially not incurring 7 wastes", then "Fix 1").

**Waste:** overprocessing. The relationship types MDM masters are written
twice: `rules/merge/relationships.yaml` (carried in the Mastering Policy) and a
code copy, `TYPES_V0` in `edgar_warehouse/mdm/clean/relationships.py`, kept
for a policy registered before the types became data. The YAML's own comment
says "the two must agree", and a test holds them equal. The default
ultimate-parent type `CALCULATED_V0` is the same kind of leftover. The rebuild
keeps no legacy behaviour (operator, 2026-09-26).

**What to build:** the types come only from the policy. A policy with no
`relationships` section is refused by name, never mastered with a code table;
an ultimate parent's type comes only from its hierarchy's `ultimate_type`.

**Blocked by:** Codex PR #1121. It rewrites `relationships.py` (the folding
moves into the source engine) and keeps the duplicate as
`CATALOG["legacy_relationships"]`; this ticket removes it from #1121's version,
so the two never conflict (as fix 2 of ticket 129: "Wait for #1121").

**Status:** in progress (Claude, branch `claude/t132-relationship-types`, 2026-10-27); was open, unblocked (2026-10-22 21:11 ET): #1121 merged (2026-10-22 19:08 ET); build on its version of `relationships.py`

## Rulings (operator, 2026-10-27)

- "No Python", then "Types in YAML + Rust only": the types and their checks live in data and the Rust engine; Python keeps no copy and no check.
- "Use RDM for keeping types and other information", then "Add code properties to RDM (Recommended)": RDM codes gain named properties; the types are an RDM code set (each type a code, its rules properties, capacities child codes); the policy pins it and the Rust engine reads the pinned rows.

- [x] Check that no registered policy a run can still use lacks the `relationships` section (the active policy, and any policy a replay reads) (2026-10-27, before 18:02 ET): the shared `working` MDM store holds 3 registered policies, every one with the section
- [x] RDM code properties: a code carries named properties (text or a list of text); PostgreSQL and MySQL migrations; draft, approve, publish, diff and context carry them; the canonical form names them only where a code has some, so every published pin is unchanged (a test over every published version); docs/specs/rdm/spec.md (2026-10-27 18:16 ET): Rust `code_properties` checks and orders them in the canonical form; migrations `005_code_properties.sql` and `mysql-properties-v4.sql`; tests: Rust 1, PostgreSQL RDM 33, MySQL migration 2 (a store published before each migration keeps its pin)
- [x] Code set `mdm-relationship-types` version 1: each type a code (its source or standard as definition), its rules properties, capacities child codes; drafted, approved and published on a disposable store (the shared server untouched); pinned in `rules/merge/reference-pins.yaml` (2026-10-27 18:41 ET): 16 types and 5 capacities (21 codes), each definition the type's plain words from `rules/context/definitions.yaml` and its source; drafted, approved (the operator's words above) and published on a disposable PostgreSQL by `.scratch/rebuild-priorities/research/132_relationship_types_draft.py`; sha256 9a0a3525…4d33; the Rust engine reads it back to exactly the YAML's types
- [x] The policy's `relationships` section is the pin; the Rust engine reads the pinned rows into typed types and refuses a missing pin, an unknown property, an unknown kind and an ultimate parent without its `ultimate_type`; policy registration calls the same Rust check (2026-10-27 18:41 ET): `relationship_types.rs` (`from_codes`, `check`, a typed rule set refusing unknown properties); `types_of` refuses a policy pinning none; registration checks a declared pin; Rust tests 2 (every refusal named)
- [x] `TYPES_V0` / `CATALOG["legacy_relationships"]` and `CALCULATED_V0` / `legacy_ultimate_type` removed; `types_of` refuses a policy with no relationship types (2026-10-27 18:41 ET): removed with `_TYPE_KEYS` and Python's own check; the engine catalog is `engine-catalog-relationship-types-in-rdm-v1`; `prepare_relationships` takes no default ultimate type
- [x] Every hierarchy with `ultimate_parent` names its `ultimate_type` in `rules/merge/relationships.yaml` (registration refuses one that does not) (2026-10-27 18:41 ET): the Rust check refuses one that does not (`test_a_type_that_could_not_run_is_refused`, "names its ultimate_type")
- [x] Tests: `tests/mdm/test_clean_relationship_types.py` and `tests/mdm/policy_layers.py` read the pinned code set only; a policy without the pin is refused; the policy layer for the move (2026-10-27 18:41 ET): policy layer `without_types_in_rdm` peels back to the previous digest exactly (81abb7cc…); test policies take the pin through `tests/support/relationship_types.py`; the frozen fixture policy pins it (digest 49cf6344…); MDM, unit and architecture 2,236 passed, integration 17 + 3 files, prepared effects 29 (PostgreSQL), RDM 33, MySQL migration 2
- [ ] Three-axis review
- [x] `rules/merge/relationships.yaml` removed (its words move into the code set's definitions) (2026-10-27 18:41 ET): and the types' words removed from `rules/context/definitions.yaml`; the agent context reads each type's definition from the code set; README and the agent-context spec name the code set
- [ ] PR merged
- [ ] Learning → skill
