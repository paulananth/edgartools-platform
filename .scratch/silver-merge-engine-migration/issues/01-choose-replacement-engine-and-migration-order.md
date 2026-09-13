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

**Status:** resolved (2026-09-13) — see "Final answer" section below. (Previously REOPENED
after the engine-choice answer was found suspect, then RE-REOPENED after a first attempted
resolution was itself found incomplete — see the CORRECTION section and the "Final answer"
section for the full history; only the "Final answer" section is current.)

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

## CORRECTION (2026-09-12, same day): "dead compute everywhere" above is wrong — retracted before any code was touched

The user invoked `/implement` on this ticket, treating the finding above as confirmed. Before
editing `merge_financial_facts`/`merge_accounting_flags`/`merge_financial_derived`, an
`advisor()` consult flagged two things this ticket's own investigation had not checked, and
both turned out to be real, disqualifying gaps:

1. **`accounting_flags.backfill_accounting_flags`** (called from `bootstrap_fundamentals.py`'s
   live `entity-facts` branch, immediately after `run_bootstrap_entity_facts` returns, in the
   *same process, same `db` connection*) does
   `silver.fetch("SELECT ... FROM sec_financial_derived WHERE cik = ? AND fiscal_period = 'FY'
   ORDER BY fiscal_year", ...)` — a direct, in-process read of exactly what
   `merge_financial_derived` just wrote. This is real, live-path consumption the "Further
   finding" above never checked (it verified `financials_derived.py`'s own *inputs* aren't a
   read-back, but never checked whether something *later in the same command* reads the
   *output* table back). Cross-period Beneish/Altman/Piotroski scoring needs multiple fiscal
   years' worth of `sec_financial_derived` rows visible at once, ordered — that's exactly what
   the local DuckDB write provides within one run.
2. **`backfill_accounting_flags` also calls `silver.update_accounting_flag_scores(cik=...,
   accession_number=...)`** — an `UPDATE` matched by `(cik, accession_number)` against
   `sec_accounting_flag`. Per that function's own comment ("Row may not exist yet; orchestrator
   writes it after entity-facts parse"), the row it updates is the one
   `merge_accounting_flags` creates earlier in the same run. `merge_accounting_flags`'s local
   write is a real prerequisite for this UPDATE to match anything.

So two of the three entity-facts merge methods are genuinely load-bearing, in-process, on the
**currently live** production path — unaffected by Ticket 10's hydration removal, because the
dependency is *within one run*, not across runs (nothing here needs the local db hydrated from
a prior run or published to a later one — it only needs to survive from one call to the next
within the same process). `merge_financial_fact`'s own table (`sec_financial_fact`) still has
no confirmed in-process reader on the live path, but the three methods are migrated as one unit
(per this ticket's own Q2 framing — they already share one per-CIK loop), so this blocks
touching any of them together.

**This reframes the actual question, back to something closer to the ticket's original
framing, but sharper:** the requirement is no longer "replicate DuckDB's `QUALIFY ROW_NUMBER()`/
`ON CONFLICT` dedup semantics somewhere durable" (Ticket 10 already proved nothing durable
needs that) — it's "hold parsed/derived rows for one CIK across one run, and let a later step
in the *same process* read them back." That's a much smaller requirement, and opens a third,
genuinely live candidate the original framing under-weighted: an **in-process Python
accumulator** (no SQL engine at all — the derived rows and accounting-flag rows are already
Python dicts before `merge_*` ever runs; `backfill_accounting_flags` could read them from a
plain per-CIK list/dict passed through the call chain instead of a DB round-trip, in-process or
not). This needs its own grilling round before any code changes: does an in-process accumulator
cover `backfill_accounting_flags`'s cross-period ordering need cleanly, or does keeping DuckDB
itself as a pure ephemeral per-run scratch store (already exactly what it is post-Ticket-10,
just never named as an intentional design) remain simpler than building a new mechanism for a
requirement DuckDB already satisfies incidentally?

**No code was edited this session.** `/implement`'s work was correctly redirected into this
correction instead, per `advisor()`'s guidance, before touching `silver_store.py`. Status
remains REOPENED — this ticket needs another grilling round on the narrower question above
before any deletion or migration proceeds.

## Superseded answer (2026-09-13, first grilling round — see below for the actual resolution)

The section immediately below this note was the original 3-round grilling answer
(Postgres for everything, marker absorbed onto this map). It was itself superseded by the
09-12 "Further finding"/CORRECTION chain above and is kept only for history — **do not
implement from it.** The real, current resolution is the "Final answer" section further
down.

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

(NOTE: this whole section above is the superseded first-round answer described at its own
top. This note repeats because the answer text above is left verbatim for history — the
`mark_entity_facts_refreshed` scope-convergence in item 2 also never happened in practice;
that marker was reverted back to the crash-resume map the same day, per the CORRECTION
section above, and stayed there. Ignore items 2 and 3's marker-related claims entirely.)

## Final answer (2026-09-13, second grilling round — this is the one to implement from)

Re-grilled after the 09-12 correction proved `merge_financial_derived`/`merge_accounting_flags`
are genuinely load-bearing in-process (via `backfill_accounting_flags`), narrowing the real
question from "port the whole trio" to "how does the specific in-run dependency get satisfied
without DuckDB." Two rounds with the operator:

**Round 1 — is full DuckDB removal a hard requirement, or is ephemeral-scratch-DuckDB an
acceptable outcome?** Operator: **full removal is required now.** No exception for a
harmless, ephemeral use — the map's destination (`duckdb` out of `pyproject.toml`/`uv.lock`)
stands as written.

**Round 1, second question — mechanism:** operator chose **Postgres, reusing the existing
bookkeeping Postgres connection** (the `bookkeeping` database on the `EDGARTOOLS_PROD_MDM`
Snowflake-hosted Postgres instance, live since duckdb-retirement-cutover Ticket 04 — same
instance MDM's own operational store lives on, different database) — not an in-process
Python accumulator. Rejected the accumulator despite it being the objectively smaller
implementation (the derived rows already exist as Python dicts before `merge_financial_derived`
ever runs) — the operator's explicit choice, not something this investigation talked them out
of.

**Round 2 — two follow-up design questions, both resolved with the recommended option:**

1. **Lifecycle:** rows are **upserted by business key, never purged**. This matches what the
   existing DuckDB-per-process flow already does in effect: each run's local db starts empty
   and only ever holds this run's own writes, so there was never any *cross-run* accumulation
   to replicate — moving to a durable Postgres table changes that only if rows are never
   updated in place. Upserting on the same `(cik, accession_number, fiscal_period, ...)` keys
   the DuckDB tables already use avoids introducing an unbounded-growth failure mode DuckDB
   never had. Revisit with an explicit purge step only if live measurement shows unwanted
   accumulation — don't build that complexity speculatively.
2. **Module boundary:** a **new, dedicated store class** (not added to `BookkeepingStore`
   itself). `BookkeepingStore`'s stated scope is non-business-content bookkeeping (checkpoints,
   leases, sync-state, run audit trail); these tables carry real, if temporary, financial-fact
   shape — a different concern from what that class exists to hold. It reuses the *same*
   Postgres connection/DSN/instance as `BookkeepingStore` (per Round 1's mechanism choice), just
   as its own class — naming and exact module location left to the implementation ticket, not
   decided here.

**Scope split this resolution surfaces, not asked as a question (follows directly from
already-established evidence, not a judgment call):**

- **`merge_financial_facts` (`sec_financial_fact`) has no confirmed in-process reader anywhere**
  (established across two prior investigation passes this session) — it does **not** need the
  new Postgres scratch mechanism at all. Its local DuckDB write is deleted outright; the
  existing `landing_export.record(...)` call inside it (which already ships the raw,
  pre-merge rows, unchanged by this whole investigation) is preserved, just no longer nested
  inside a DuckDB write — a direct call at the same point in the caller, not routed through
  `SilverDatabase` at all.
- **`merge_accounting_flags`/`merge_financial_derived` are the two tables that actually need
  the new Postgres-backed scratch store**, because `backfill_accounting_flags` (called
  immediately after, same process) reads `merge_financial_derived`'s output back for
  cross-period scoring and requires `merge_accounting_flags`'s row to already exist for its own
  `UPDATE` to match.
- **`mark_entity_facts_refreshed` stays on the crash-resume map**, unaffected by any of this
  (confirmed settled in the CORRECTION above and never revisited here).

**Migration order (revised from the superseded answer's item 3, given the split above):**

1. `merge_financial_facts` — pure deletion + landing-export passthrough. Simplest, no new
   store needed, ships first as a quick, low-risk win.
2. `merge_accounting_flags` + `merge_financial_derived` together, with `backfill_accounting_
   flags` rewired to read from the new Postgres scratch store instead of local DuckDB — the
   real work this ticket exists to unblock. These two are inherently coupled (one function
   consumes both), so they move as one unit, not sequentially.
3. `per-filing`/`thirteenf` modes' own merge methods — **confirmed this session (not assumed)**
   that neither shares the entity-facts trio's in-process read-back shape: both
   `run_bootstrap_fundamentals_per_filing`/`run_bootstrap_thirteenf` only ever write via
   `db.merge_*`, with zero downstream read of what they just wrote within the same run. Each
   can very likely just delete-and-passthrough-to-landing-export the same way
   `merge_financial_facts` does — to be individually confirmed per table before deleting, not
   assumed from this one similarity.
4. `company-identity` mode — unchanged from the original framing: assess once reached, may be
   trivial or nonexistent.

**"Done" bar per table** (unchanged from the superseded answer, still correct): equivalent
regression coverage to the existing merge tests (`test_silver_protection_scoped_merge.py`,
`test_silver_financial_fact_retirement_provenance.py`, `test_silver_store_schema_migration.py`,
etc. — kept as the executable spec, updated for the new behavior rather than deleted) plus a
live-verified production write showing correct output.

**New fog surfaced, not resolved here:** `retire_financial_facts_not_in_snapshot`/
`retire_accounting_flags_not_in_snapshot` (Ticket 33's retirement writes,
`company_facts_silver_acceptance.py`'s only caller) operate on the exact DuckDB tables item 1
above deletes/item 2 moves off DuckDB — their fate isn't decided by this ticket and needs its
own look once the split above actually lands (their only caller is dormant/unscheduled today,
per the 09-12 finding, which may make this low urgency, but "unscheduled today" isn't the same
as "safe to ignore" if that driver is ever wired in).

## CORRECTION (2026-09-13, third round, at implementation time): item 2's Postgres scratch store is wrong — superseded by in-memory scoring

Caught by the operator when implementation of Ticket 03 started ("ticket 01 is wrong for
storing prior-year financial numbers such as revenue, total assets or net income" in a
Postgres scratch store). The Final answer above kept `sec_accounting_flag`/
`sec_financial_derived` on a durable store because `backfill_accounting_flags` read the
derived rows back and UPDATEd the flag rows — but it never asked *where those rows came from*.
They come from the same SEC companyfacts payload the same `run_bootstrap_entity_facts` loop
iteration just parsed, and that payload carries the company's **entire** filing history
(every fiscal year), not just the new filing. So every input the cross-period Beneish/Altman/
Piotroski math needs is already in memory, per CIK, before any write happens. A store —
Postgres, DuckDB, anything — was only ever a detour back to data the process was already
holding.

Grilled with the operator (three rounds, all agreed):

- **Scoring is in-memory, per company**, inside the per-CIK loop: a pure
  `score_accounting_flags(flag_rows, derived_rows)` replaces `backfill_accounting_flags` +
  `update_accounting_flag_scores`; the scored flag rows are what `merge_accounting_flags`
  records. No Postgres scratch store, no new store class, no migration.
- **No new Snowflake silver table.** The operator's condition was "if the in-memory value is
  calculated per company it is fine; if not, the final number goes to a new silver table." It
  is per company, and the final numbers already land in `EDGARTOOLS_SILVER.SEC_ACCOUNTING_FLAG`
  (scores) and `SEC_FINANCIAL_DERIVED` (metrics) via the landing export + dbt collapse.
- **A CIK the skip gate skips keeps its last scores in silver** — same as the DuckDB design
  behaved; a company's history only changes when it files, and a new filing lets it through
  the gate, which rescores its full history.
- **`retire_financial_facts_not_in_snapshot`/`retire_accounting_flags_not_in_snapshot` are
  deleted** (the "new fog" item above, resolved): they found rows to retire by reading local
  DuckDB, which nothing writes anymore; their only caller (company-facts acceptance) has no
  landing export wiring and a no-op publish, so its retirements never reached Snowflake even
  before. Acceptance now marks a producer VERIFIED once its rows are recorded. Retirement
  against Snowflake silver (via the existing Ticket 35 Silver Landing Retirement Record
  mechanism, which needs the prior membership read from Snowflake) is fog on the map.
- **A row missing a NOT NULL column raises before recording** (keeps DuckDB's fail-loud
  behaviour; Snowflake landing's NOT NULL would otherwise reject the whole Parquet file).
- **`ingested_at` is stamped per write on fact and flag landing rows** (DuckDB used to supply
  it via DEFAULT; gold `accounting_flags` outputs it). Derived rows stay as they are today.

Net effect on the Final answer: item 1 (Ticket 02, delete + passthrough) stands; item 2
(Ticket 03) becomes "delete + passthrough as well, with the scoring moved in-process" — the
whole entity-facts trio is now the same shape. Ticket 03's body rewritten to match.
