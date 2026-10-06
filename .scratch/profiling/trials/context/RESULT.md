# Ticket 05: the `context` command on real data

Run on 2026-10-06 against ticket 04's seeded GLEIF slice: the local golden
copies, with no request to any provider. The slice was loaded through the real
GLEIF contracts and the Mastering Policy in `rules/`, in two batches: entities
as of 2026-09-11 16:00 UTC, then links as of 2026-09-12 16:00 UTC. Script:
`check_context.py`; numbers: `context-check.json`.

- **The store:** 679 live entities in `mdm.entity_context`.
- **What was asked:** 60 seeded entities. Each one got a lookup by id, a lookup
  by its LEI, a search by the first word of its name, an `--as-at` lookup at
  the first batch, an `--as-of` lookup and the relationship walk at 1, 2 and 3
  hops. That makes 480 answers.

| Check | Result |
|---|---|
| Lookup by id finds the entity | 60 / 60 |
| Lookup by `lei:<value>` finds the same entity | 60 / 60 |
| Search by the first word of the name lists it (top 20) | 60 / 60 |
| `--as-at` the first batch reads generation 1 | 60 / 60 |
| `--as-of` a time between the batches reads generation 1 | 60 / 60 |
| Relationship walk answers at 1, 2 and 3 hops | 60 / 60 each |
| Walks cut by size and paged (3 hops) | 3 |
| Answers over 8 KB | 0 (largest 8,151 bytes) |

**Time per answer:**
- the median is 4–58 ms;
- the slowest was 116 ms, an `--as-of` lookup, which reads every field's provenance through the version-2 reader.

**Not covered here:**
- **Person links with roles** are covered by the PG16 tests; GLEIF has none.
- **Relationships `--as-at`** is not built, and the command says so (ticket decision).
