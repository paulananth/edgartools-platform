# MDM Entity Resolution Ahead of Silver

Label: `wayfinder:map`

## Destination

An implementation-ready plan for inserting MDM's match/merge/survivorship
step between silver's document-parsing step and its DB commit — so parsed
records carry a resolved `mdm_entity_id` (across all six entity types) by
the time they land in silver, instead of MDM resolving entities only after
silver is already complete (today's order: parse → silver commit → MDM
reads silver). Reaching the end of this map means someone can start
implementing without hitting an undecided design question: the coupling
mechanism between MDM and silver's write path, which write-path commands
are in scope, resolution batch granularity/algorithm risk, cold-start
behavior, and the interaction with the still-in-flight silver-on-Snowflake
migration are all settled.

## Notes

- Grounding, already established via this session's grilling — do not
  re-derive:
  - MDM consumes already-parsed records (the same Python dicts
    `silver_store.py`'s parsers build via `edgar_warehouse/parsers/
    ownership.py`, `adv.py`, XBRL extraction) — **not** raw bronze bytes.
    MDM does not gain its own SEC-document parsing; it inserts itself
    between "parse" and "silver DB commit," not between "bronze bytes" and
    "parse."
  - All six entity types (company, adviser, person, security, fund,
    audit_firm) get resolved up front, uniformly — not just the ones where
    cross-filing identity is genuinely ambiguous (person/security/
    adviser/fund). Company/audit_firm are included even though their
    business keys (CIK, PCAOB firm ID) are already close to unambiguous.
  - Silver's own dedup/merge logic (`silver_protection.py`'s business-key
    merge) is **unchanged**. The concrete deliverable is a new
    `mdm_entity_id` column populated on the relevant silver tables before
    commit — MDM's matching engine does not replace silver's merge
    mechanics.
  - Resolution stays batch-shaped: one CIK window's worth of parsed
    records gets resolved as a batch, immediately before that window's
    silver commit — preserving `match.py`'s existing batch-context
    algorithms (bulk prefetch, confirmed via `pipeline.py`'s own comments
    — not per-row lookups) rather than rewriting them for per-row/
    streaming operation.
- **Explicit relationship to the closed
  [silver-snowflake-migration](../silver-snowflake-migration/map.md) map**:
  that map already decided silver's canonical store moves to a Snowflake
  landing zone (append-only, Python-populated, real ingestion live in prod
  since its Ticket 07) plus dbt-native collapse, and separately that MDM's
  `ShardedSilverReader` retires in favor of Snowflake-native GRANTs on a
  dedicated reader role (its Ticket 03) — but that only addressed MDM's
  **read** mechanism, never its **pipeline ordering** relative to silver.
  The coupling-mechanism ticket on this map must be decided with that
  target architecture in mind, not just today's DuckDB flow — the user
  flagged this directly ("silver will eventually move to snowflake")
  rather than letting the coupling design get built for a storage layer
  that's already slated to be replaced.
- **Explicit relationship to the open
  [Extend Sharded Silver Writes to Primary Ingestion](../silver-sharded-writes/map.md)
  map**: that map narrowed sharded-write extension to exactly two primary
  write surfaces — `WindowedBootstrap` (`load_history` Stage 1) and
  `bootstrap_fundamentals.py` (Stage 1B) — because `daily_incremental`/
  `bootstrap`'s default invocation are structurally cross-shard (needs
  single-owner-per-shard, which they can't guarantee) and need new
  engineering those two don't have yet. **[Decide Write-Path Command
  Scope](issues/03-decide-write-path-command-scope.md) found this
  narrowing does NOT transfer to this map**: MDM's candidate pool lives
  in its own Postgres, not CIK-sharded silver storage, so the
  cross-shard blocker doesn't apply. Four of five commands share one
  write site (`_run_submissions_bronze_then_silver`) and are in scope
  uniformly here — a different, wider scope than the sharded-writes map
  reached for a structurally similar-looking problem. Documented as a
  cautionary example: a narrowing decided for one constraint doesn't
  automatically transfer to a different constraint on the same
  commands, even when the framing looks parallel.
- MDM domain code: `edgar_warehouse/mdm/pipeline.py` (`MDMPipeline`
  orchestrator — company→adviser→security→person→fund dependency order,
  today reads from silver via a `SilverReader` protocol issuing typed
  SQL), `match.py`/`survivorship.py` (matching algorithms, incl. an
  `ml_splink` method), `resolvers/` (per-entity-type resolvers),
  `database.py` (the 25-table Postgres schema — see this session's MDM ER
  diagram artifact for the full shape).
- This repo has documented incidents from getting cross-stage
  sequencing/coupling assumptions wrong (CLAUDE.md's
  "INSTITUTIONAL_HOLDS/EMPLOYED_BY" and "Manifest-pipeline ownership +
  cursor-syntax incident" 5-whys) — every ticket here should weigh that
  history explicitly, the same standing note the other two active/recent
  maps carry.
- Use `/gof-refactor-reviewer` before any ticket proposing to restructure
  `pipeline.py`'s orchestration or the warehouse runtime's write path, per
  this repo's standing CLAUDE.md instruction.
- Mode: decision-spec only (wayfinder default, not overridden).
  Implementation is a separate, later effort.

## Decisions so far

<!-- Closed ticket decisions: one-line gist and link; detail stays in the ticket. -->

- [Decide the Coupling Mechanism Between MDM and Silver's Write Path](issues/02-decide-coupling-mechanism.md) — two-phase/decoupled, uniformly for both targets: parse writes `mdm_entity_id = NULL` immediately; MDM resolves the window shortly after and backfills — a second landing-zone `INSERT` (dbt's latest-`parse_sequence`-wins collapse handles it natively, no new capability needed) for Snowflake, a normal `UPDATE` via `silver_protection.py`'s existing merge path for DuckDB. Rejected synchronous/blocking — would couple every in-scope write path's progress to MDM Postgres's live availability.
- [Confirm Match Candidate-Prefetch Behavior Under Per-Window Batching](issues/01-confirm-match-candidate-prefetch-behavior-under-per-window-batching.md) — company/person/security resolution already does live per-row queries (per-window batching costs nothing extra); adviser/fund resolution does an unscoped full-table prefetch that would multiply ~124× under per-window batching (window size 500, ~62K-company universe), and separately `run_advisers`/`run_funds` have no CIK-scoping parameter at all yet — a capability gap, not just a cost question, for ticket 03 to account for.
- [Decide Write-Path Command Scope](issues/03-decide-write-path-command-scope.md) — corrected the map's own premise first: all 5 commands share one write site (`_run_submissions_bronze_then_silver`), so the silver-sharded-writes map's 2-of-5 narrowing doesn't transfer (that constraint was storage-sharding-specific; MDM's candidate pool lives in its own Postgres, not CIK-sharded silver). Scope: `bootstrap-next`, `bootstrap`, `bootstrap-full`, `daily-incremental` — four of five, uniformly, via one shared insertion point. `bootstrap-batch` excluded — its records are already MDM-resolved from original ingestion, and its `MaxConcurrency=3` would introduce a new backfill-race hazard the other four don't have.
- [Decide Cold-Start / Bootstrap Behavior](issues/04-decide-cold-start-bootstrap-behavior.md) — not a new risk class: today's after-silver Stage 2 pass already processes rows sequentially against a live, incrementally-growing MDM Postgres candidate population (`run_companies`/`run_persons` are already order-dependent), so per-window resolution is the same model, just chunked differently — no mitigation required. A periodic full-universe backstop/reconciliation pass is a legitimate future idea for catching near-miss matches, but isn't required for correctness and isn't designed by this map.
- [Decide Failure/Retry Semantics for the Two-Phase Backfill](issues/05-decide-backfill-failure-retry-semantics.md) — independent sweep, reusing this codebase's existing NULL-pending pattern (`mdm_change_log.exported_at`/`mdm_relationship_instance.graph_synced_at`, both nullable + partial index + separate sweep). A window's command only ever writes `mdm_entity_id = NULL` and exits — never attempts resolution itself. The sweep's own repeated passes are the retry mechanism; stuck NULLs past a threshold alert, matching this repo's no-silent-failure philosophy.

## Not yet specified

<!-- empty — the only remaining fog graduated into ticket 05 -->

- A periodic full-universe backstop/reconciliation pass (noted in ticket
  04's answer) remains a legitimate future idea, not yet specified as a
  ticket — it isn't required by anything this map has decided, so it's
  left as a loose pointer for a possible future map rather than forced
  into a ticket here.

## Out of scope

- **`bootstrap-batch`** — ruled out during [Decide Write-Path Command
  Scope](issues/03-decide-write-path-command-scope.md). It's a secondary
  reprocessing pipeline over already-loaded bronze whose records already
  carry an `mdm_entity_id` from their original ingestion via one of the
  other four commands — re-resolving here is redundant. Also sidesteps a
  genuine new correctness risk: it runs at `MaxConcurrency=3`, and
  two-phase resolution's backfill INSERT/UPDATE could race across
  concurrent batches touching the same adviser/security/CIK, a hazard
  none of the other four commands have today (they never run concurrently
  with each other). Not ruled out forever — revisit if `bootstrap-batch`'s
  role ever changes to include fresh entity discovery.
