# 182: The "other" capacity of a reporting owner has a real relationship type

Priority: 182. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 13:55 ET, from [143](143-silver-keeps-no-master-field.md) (silver keeps no master field).

Type: task. Status: open. Blocked by: none.

## Question

A Form 3, 4 or 5 lets a reporting owner state a fourth capacity at the issuer, "Other (specify below)", with free text (`is_other`, `other_text`). The ownership Dataset Contract maps three capacities (director and officer as EMPLOYED_BY, ten-percent owner as BENEFICIAL_OWNER_OF); the fourth has no relationship type, so MDM does not hold it and `insider_ownership` still keeps `is_other` and `other_text` (the one master-data fact left in silver). Which real relationship type, from the standard SEC and the platform's relationship types name, holds it, and with what capacity and title?

## Parts

- [ ] Count the owners that state "other" in the captured Forms 3, 4 and 5, and list the distinct texts (counts and shapes only)
- [ ] Name the relationship type the platform's pinned relationship types already hold for it, or the standard word for a new one (a real name, never an invented one)
- [ ] Map it in the Dataset Contract (`held: is_other`, `title: other_text`), then drop `is_other` and `other_text` from `insider_ownership` (silver register under a new table name: the spec change is refused for a registered table)
- [ ] Learning → skill
