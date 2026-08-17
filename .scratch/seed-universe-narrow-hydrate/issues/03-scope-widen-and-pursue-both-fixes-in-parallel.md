# 03 — Scope: widen destination to the shared streaming-buffer fix, pursue both fixes in parallel

Type: grilling
Status: resolved
Blocked by: 02-non-streaming-hydrate-buffer-shared-root-cause (the finding
that made this decision necessary)
Blocks: 04, 05

## Question

Ticket 02 found that `seed-universe`'s OOM shares a root cause with three
other already-bumped commands (Stage0CompanyIdentity, ComputeWindows,
gold-refresh): `_hydrate_silver_database_from_storage`'s non-streaming
full-object buffer. This map was explicitly scoped narrow to `seed-universe`
before that was known ("A, replace, narrow to seed-universe", prior
grilling round). Two live questions for the user:

1. Does this finding widen the map's destination to the shared
   streaming-buffer fix (general, benefits all four commands), or does the
   map stay narrow to `seed-universe` and treat the streaming fix as an
   out-of-scope follow-up?
2. Given the streaming fix addresses the download-buffer cost but not the
   need for a local on-disk copy, is the DuckDB `httpfs` narrow-read
   mechanism (ticket 01, feasible for read only) still worth pursuing for
   `seed-universe` specifically, or should it wait to see if the streaming
   fix alone is sufficient?

## Answer

User: **widen the destination, and pursue both fixes in parallel** --
the shared streaming-buffer fix (general, all hydrate-consuming commands)
and the `httpfs` narrow-read mechanism (specific to `seed-universe`'s
read-only `get_active_ciks` path) both proceed as part of this map's
outcome, not sequenced one-after-the-other.

Map's Destination and Notes updated accordingly (see map.md). This does
not retire ticket 01's finding or the original narrow-`seed-universe` write
constraint (write still can't go through remote `httpfs` at any DuckDB
version) -- it adds a second, complementary track rather than replacing the
first.
