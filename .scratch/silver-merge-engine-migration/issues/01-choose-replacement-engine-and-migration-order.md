# 01 — Choose the replacement engine and migration order

**Type:** grilling

## Question

Two coupled decisions block every downstream migration ticket:

1. **Which engine replaces DuckDB for the merge/dedup compute** — the leading candidate is
   Postgres (the BookkeepingStore precedent already lives there, and it natively supports
   window functions + `ON CONFLICT` upserts with equivalent semantics to DuckDB's
   `QUALIFY ROW_NUMBER() OVER (...)`/`ON CONFLICT ... DO NOTHING`), but this needs to be
   weighed against the real cost DuckDB is currently avoiding: today's merge runs as local,
   in-process SQL with no network round trip; moving it to Postgres means every
   `bootstrap-fundamentals` task pays real network latency per merge operation, potentially at
   a volume DuckDB never had to think about. An in-process alternative (pure Python/pyarrow
   dedup logic, no external SQL engine at all) is the other real candidate, trading query
   expressiveness for zero network cost. Decide which, and why.
2. **Migration order across the affected merge methods** — `merge_financial_facts`,
   `merge_accounting_flags`, `merge_financial_derived`, `mark_entity_facts_refreshed`, and their
   `per-filing`/`thirteenf`/`company-identity`-mode equivalents. Pick a first table (the
   crash-resume map already has `mark_entity_facts_refreshed` mid-move to BookkeepingStore —
   confirm whether that supersedes or complements this map's own first step) and define what
   "this table is done" means: equivalent regression coverage to the existing merge tests, plus
   a live-verified production write showing correct output.

Resolve via `/grilling` + `/domain-modeling`, per this map's own Notes.

**Blocked by:** none — this is the map's frontier ticket.

**Status:** open
