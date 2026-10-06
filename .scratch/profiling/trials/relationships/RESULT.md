# Ticket 04 on real data: the MDM parent chain against GLEIF's own data

2026-10-06, 08:07 to 08:13 ET. Local copies of the GLEIF golden copies of
2026-09-11 16:00 only; no request to any provider.

**Result: wherever MDM holds both ends, `mdm.relationship_chain` ends exactly
where GLEIF's own direct-parent chain ends.** It ends at GLEIF's stated
ultimate parent for 273 of 284 entities. In the other 11, GLEIF's stated
ultimate parent disagrees with GLEIF's own direct chain, and MDM reproduces
the source faithfully. The engine's calculated ultimate parent agrees in all
273.

## How

1. `slice_gleif.py`: of 126,665 active direct and 132,836 active ultimate
   consolidating links, a seeded sample (seed 0) of 300 entities stating both.
   Each direct chain is walked, keeping 694 relationship records and the 698
   Level 1 records they touch. The entity file streams once in 7.5 minutes.
2. `check_chains.py`: on a local PostgreSQL 16, the slice is read through the
   real GLEIF contracts and the Mastering Policy in `rules/` (with its
   relationship types). Each Level 1 record is bound to its own Company, as a
   steward would bind it. For each sampled entity, the end of
   `mdm.relationship_chain(entity, 'IS_DIRECTLY_CONSOLIDATED_BY', 50)` is
   compared with the ultimate parent GLEIF states, and with the source's own
   chain.

## Outcome (`chain-check.json`, cross-tabulated by `compare.py` into `compare.json`)

| Source's own direct chain | MDM | Entities |
|---|---|---|
| ends at the stated ultimate parent | chain ends at the stated ultimate parent | 273 |
| ends elsewhere (GLEIF disagrees with itself) | chain ends at the same entity as the source's chain | 11 |
| ends at the stated ultimate parent | an end is not a Company in MDM | 12 |
| ends elsewhere | an end is not a Company in MDM | 4 |

- 19 Level 1 records are set aside as `unsupported_identity_kind`: GLEIF
  categories the Company contract does not take (funds, sole proprietors,
  government entities). Their links wait (`unresolved_endpoint`, 30 reviews),
  which is why 16 sampled entities cannot be checked.
- No relationship record was refused.

`compare.py` walks each sampled entity's direct chain in the slice's own
relationship records and compares the entity it ends at with the entity
MDM's chain ends at: the same for all 284 checkable entities. Rerun
2026-10-06 08:16 ET with the chain function after review (scope, time, hop limit).
