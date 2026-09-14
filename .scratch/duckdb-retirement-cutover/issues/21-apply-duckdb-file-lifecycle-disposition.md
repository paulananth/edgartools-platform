# 21 — Apply DuckDB file lifecycle disposition (S3 archive/delete)

**What to build:** Apply DuckDB file disposition for the canonical `silver.duckdb`/shard
objects still in S3, per DuckDB Retirement's Ticket 01 answer: extend the existing
`expire-noncurrent-silver-canonical-versions` lifecycle-rule precedent -- bounded
retention on the final current version, then archive/delete.

Split out of Ticket 12 because it is irreversible against shared production data and
gated on a different, currently-open dependency: [Ticket 19](
19-sec-company-ticker-cross-store-divergence.md)'s own Done-when criterion requires "a
repeat `table-reconcile --tables sec_company_ticker` run passes clean afterward" -- which
needs both the DuckDB side of that comparison and the live 1.79GB canonical object to
still exist. Applying disposition before Ticket 19 resolves would remove the evidence
needed to close it.

**Blocked by:** nothing since 2026-09-14 ([Ticket 19](19-sec-company-ticker-cross-store-divergence.md)
closed as explained, its evidence recorded in the ticket, so the DuckDB file is no longer needed
to close it). Still requires explicit operator go-ahead separately (destructive action on shared
prod infrastructure, not something to execute on an inferred approval).

**Status:** open

- [x] Ticket 19 resolved (closed 2026-09-14 as explained)
- [ ] Explicit operator go-ahead obtained for this specific disposition action
- [ ] Bounded retention + archive/delete applied to the canonical `silver.duckdb`/shard S3
      objects, following the `expire-noncurrent-silver-canonical-versions` precedent
