# 182: The "other" capacity of a reporting owner has a real relationship type

Priority: 182. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 13:55 ET, from [143](143-silver-keeps-no-master-field.md) (silver keeps no master field).

Type: task. Status: resolved. Blocked by: none.

## Question

A Form 3, 4 or 5 lets a reporting owner state a fourth capacity at the issuer, "Other (specify below)", with free text (`is_other`, `other_text`). The ownership Dataset Contract maps three capacities (director and officer as EMPLOYED_BY, ten-percent owner as BENEFICIAL_OWNER_OF); the fourth has no relationship type, so MDM does not hold it and `insider_ownership` still keeps `is_other` and `other_text` (the one master-data fact left in silver). Which real relationship type, from the standard SEC and the platform's relationship types name, holds it, and with what capacity and title?

## Parts

- [x] Count the owners that state "other" in the captured Forms 3, 4 and 5, and list the distinct texts (counts and shapes only) — 2026-11-03 17:11 ET. The only Form 3/4/5 capture on this machine is the profiled cohort (3,367 owner rows; the full capture is not local, so the full count waits for it). In it 7 owner rows carry other text (0.2%), 3 distinct texts, all three refine a real capacity: 4 rows a board-chair title, 2 rows a former ten-percent holder, 1 row a director by deputization. None names a fourth kind of relationship. Source: the cohort profile `findings.yaml` (`reportingOwnerRelationship.otherText`).
- [x] (2026-11-03 17:21 ET) Name the relationship type the platform's pinned relationship types already hold for it, or the standard word for a new one (a real name, never an invented one) — operator ruling 2026-11-03 17:15 ET, "Capacity `other` on EMPLOYED_BY (Recommended)": the form's own word `other` becomes a fourth capacity of EMPLOYED_BY (relationship types version 2, a new published version and pin), the stated text its title
- [x] (2026-11-03 17:21 ET) Map it in the Dataset Contract (`held: is_other`, `title: other_text`), then drop `is_other` and `other_text` from `insider_ownership` (silver register under a new table name: the spec change is refused for a registered table) — done: contract maps `held: is_other, title: other_text`; both columns moved from the reading's silver table to its owner record; silver table is `insider_reporting_owner`; verified by tests/unit/test_silver_keeps_no_master_field.py, test_rules_mapdoc.py, test_clean_relationship_types.py and test_ownership_silver.py
- [x] (2026-11-03 17:21 ET) Learning → skill: `skills/mdm-engineering/SKILL.md` (a new capacity is a new published version and pin; count a field's rows before naming a type for it)
