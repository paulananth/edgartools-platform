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

**Status:** REOPENED (2026-09-13) — see correction below. The engine-choice answer (Postgres)
is now in doubt; the scope/marker-absorption answer was wrong and reverted.

**CORRECTION (2026-09-13):**

1. **Scope/marker absorption reverted.** The `mark_entity_facts_refreshed` marker does NOT
   belong on this map — it's a crash-resume/idempotency concern, not a merge/dedup-compute
   concern, and it already has an existing, proven solution (the pipeline-resumability map's
   resume-ledger pattern, live in `company_resume.py`/`daily_artifact_resume.py`). Moved back
   to the bootstrap-fundamentals-crash-resume map as a `task` (design question dissolved —
   just apply the existing pattern). This map's Tickets 02/03 (which briefly held this) are
   deleted.
2. **Engine choice (Postgres) is now suspect.** Investigating the reverted marker exposed a
   fact that directly undermines the original Q1 framing: `merge_financial_facts`'s
   `landing_export.record(...)` call ships the **raw, pre-merge, undeduped `rows`** to the
   Snowflake landing zone — not DuckDB's `QUALIFY ROW_NUMBER()`/`ON CONFLICT`-deduped output.
   And the dbt silver model (`infra/snowflake/dbt/edgartools_gold/models/silver/
   sec_financial_fact.sql`) independently re-implements the **identical** first-seen/
   last-seen `QUALIFY ROW_NUMBER()` dedup logic directly against those raw landing rows
   (its own comment: "matches silver_store.py's merge_financial_facts two-pass upsert
   exactly"). This means DuckDB's local merge/dedup SQL may be computing a result that is
   **never consumed by anything** — the local ephemeral DuckDB file is discarded at task end
   (Ticket 10), and the real, authoritative dedup for what reaches canonical
   `EDGARTOOLS_SILVER` already happens in dbt/Snowflake, independently of DuckDB's work.

   **If confirmed**, the right fix is not "port the merge SQL to Postgres" — it's "delete the
   local DuckDB merge/dedup call entirely, write parsed rows straight to `landing_export`."
   Dramatically simpler than a Postgres port, and much closer to "duckdb actually gone."

   **Not yet confirmed — the one open question before re-deciding:** does anything else
   *within the same task process* read the local DuckDB `sec_financial_fact` table
   post-merge (e.g. `financials_derived.py`'s `sec_financial_derived` computation, or an
   in-process idempotency check)? If yes, the local merge/dedup still does real, necessary
   work for *this task's own* downstream steps, independent of what reaches Snowflake, and
   the Postgres-vs-delete question needs re-litigating with that constraint in mind. If no,
   the merge call is provably dead compute and can simply be deleted.

This ticket is reopened pending that check — do not resume table-by-table migration
(Tickets 02+) until it's answered.

## Answer

Resolved via a 3-round grilling session with the operator, 2026-09-13.

1. **Engine: Postgres.** Leverages the BookkeepingStore precedent already live in this
   repo; Postgres natively supports window functions and `ON CONFLICT` with equivalent
   semantics to DuckDB's `QUALIFY ROW_NUMBER() OVER (...)`/`ON CONFLICT ... DO NOTHING`.
   Accepted trade-off, not yet measured: every `bootstrap-fundamentals` task now pays
   real network round-trips per merge instead of local in-process SQL.
2. **Scope convergence: this map absorbs `mark_entity_facts_refreshed`'s move**,
   superseding the bootstrap-fundamentals-crash-resume map's own open Tickets 02/03
   (design + implementation of that exact marker's move to BookkeepingStore/Postgres) —
   rather than two maps independently designing the same move. Those two tickets are
   moved into this map as Tickets 02/03 (content carried over, not re-designed from
   scratch); the crash-resume map's originals are marked superseded with a pointer here.
3. **Migration order:** `mark_entity_facts_refreshed` (this map's Tickets 02/03) first,
   then the entity-facts trio — `merge_financial_facts`/`merge_accounting_flags`/
   `merge_financial_derived` — together (highest value: this is the exact code path that
   OOM-crashed 3x, and all three already share one per-CIK loop so proving the Postgres
   pattern once covers all three). `per-filing` and `thirteenf` modes' own merge methods
   follow after that. `company-identity` mode last, or skipped outright if its own merge
   logic turns out to be trivial/nonexistent once reached (not yet confirmed either way).
4. **"Done" bar per table** (uncontested, carried over from this ticket's own framing):
   equivalent regression coverage to the existing merge tests
   (`test_silver_protection_scoped_merge.py`, `test_silver_financial_fact_retirement_
   provenance.py`, `test_silver_store_schema_migration.py`, etc. — kept as the executable
   spec, not deleted) plus a live-verified production write showing correct output.
