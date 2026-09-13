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

## Further finding (2026-09-12): the discriminating question is now answered, decisively, by a cutover that already shipped

Investigated the one open question above (does anything in-process read the local merged
table post-merge) by tracing every real reader of `sec_financial_fact`/`sec_accounting_flag`
in the repo, not just the legacy `run_bootstrap_entity_facts` path the prior finding checked:

1. **The legacy path** (`fundamentals_ingest.run_bootstrap_entity_facts`, what
   `bootstrap-fundamentals --mode entity-facts` actually runs in prod today — confirmed via
   `infra/scripts/pipeline_stage_helpers.py`'s `fundamentals_mode_stage`, the builder behind
   `load_history`/`daily_incremental`'s `FetchEntityFacts` stage): `compute_derived_for_accession`
   is called with `fact_rows=parsed.get("sec_financial_fact", [])` — the raw in-memory parsed
   rows, not a DB read-back. Confirms the prior finding: nothing here reads the merged table.
2. **A second, newer path exists and does read it back** —
   `edgar_warehouse/acquisition/company_facts_silver_acceptance.py` (wired in via
   `drive-company-facts-discovery`, Ticket 22 of the **Incremental Change Propagation**
   wayfinder map, `.scratch/change-propagation/`). After `silver.merge_financial_facts(...)`,
   it runs `SELECT DISTINCT accession_number FROM sec_financial_fact WHERE cik = ? AND
   accession_number IN (...)` to verify the write, and gates
   `silver.retire_financial_facts_not_in_snapshot(...)` (a real Ticket-33 retirement write) on
   that verification passing. This looked, at first, like the load-bearing in-process reader
   this ticket's blocking question was waiting on — until checking whether it's actually live.
3. **It isn't, and more importantly, it can't matter even when it runs.** Two independent
   facts close this off:
   - `drive-company-facts-discovery` has **zero scheduled presence in any state machine**
     (confirmed via `deploy-aws-application.sh` — matches change-propagation's own Ticket 10
     finding: "the new ledger-gated drivers have zero scheduled presence in prod today").
   - Far more decisively: **DuckDB Retirement Cutover's Ticket 10 (the atomic write-path
     cutover) is now deployed live** (confirmed 2026-09-12, this same day — see that ticket's
     own "Correction" section). It explicitly retired hydrate/publish for exactly this driver:
     `drive_company_facts_discovery.py:118-122`'s own comment reads *"DuckDB Retirement Cutover
     Ticket 10: hydration removed... canonical silver.duckdb is no longer written by any
     command."* `db = open_silver_database(context.silver_root)` now opens a **fresh, never-
     hydrated** local DuckDB every run, and `_publish_silver_database_with_retry` is now a
     permanent no-op. So even on a run where this driver *did* execute: the read-back check
     verifies data against the *same ephemeral session that just wrote it* (trivially true
     barring a genuine SQL bug — no longer proof of durable persistence), and
     `retire_financial_facts_not_in_snapshot`'s comparison basis (`is_current=TRUE` rows from
     a *prior* snapshot) is always empty, since the local db starts empty every run with
     nothing carried over from the last one. The retirement mechanism this whole read-back
     dance exists to gate is now structurally incapable of ever finding anything to retire.

**Conclusion: the local DuckDB merge/dedup engine is dead compute everywhere, not just on the
legacy path.** Ticket 10's cutover — decided independently on the parent `duckdb-retirement`
wayfinder map (`.scratch/duckdb-retirement/`, Destination: "the production write path stops
writing `silver.duckdb` entirely (Snowflake landing zone only)") and implemented via
`duckdb-retirement-cutover`'s own Ticket 09/10 — already severed *every* production and
near-production code path from ever reading back what `merge_financial_facts`/
`merge_accounting_flags` compute locally. Combined with the earlier finding (dbt's
`sec_financial_fact` silver model already independently re-implements the identical dedup
logic against the raw, undeduped landing rows), there is no longer a plausible "something
still needs it" case left to check.

**This also means the original engine-choice framing (Postgres vs. delete) is resolved by a
decision this ticket does not need to re-litigate — it was already made, at the parent map
level, before this child map (silver-merge-engine-migration) was even charted.** The
`duckdb-retirement`/`duckdb-retirement-cutover` maps already decided and shipped "no local
merge engine of any kind, write straight to the Snowflake landing zone" for the write path in
general. This ticket's real remaining scope is narrower than originally framed: not "choose a
replacement engine," but "delete the now-confirmed-dead local merge/dedup calls
(`merge_financial_facts`/`merge_accounting_flags`/`merge_financial_derived`, plus their
`per-filing`/`thirteenf`/`company-identity` equivalents once each is individually confirmed
the same way) and, where a caller like `company_facts_silver_acceptance.py` still wants a
write-verification signal, replace the DuckDB read-back with a check against what was actually
written to the Snowflake landing export instead."

Presented to the user for confirmation before writing the final Answer below — this ticket is
`grilling` (HITL), so the decision is recorded once the user has weighed in, not decided
unilaterally from this evidence alone.

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
