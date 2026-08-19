# 02 — Verify ordering-safety for every stage-pair whose relative order changes

Type: research
Status: resolved
Blocked by: 01

## Question

Given Ticket 01's final phase classification, enumerate every pair of
stages whose relative execution order **flips** from install.sh's current
sequence (i.e. stage A currently runs before stage B, but under the new
phase order B would run before A). For each flipped pair, verify — by
reading the actual delegate scripts, not by guessing — whether a real
dependency breaks:

- `infra/scripts/deploy-snowflake-stack.sh`
- `infra/scripts/deploy-aws-application.sh`
- `infra/scripts/bootstrap-prod-mdm.sh`
- `infra/scripts/install-neo4j-graph-app.sh`
- `infra/snowflake/sql/bootstrap/07_mdm_export_targets.sql`,
  `08_loader_role.sql`, and any other bootstrap SQL touched by a flipped
  pair
- `infra/snowflake/postgres/mdm_create_network_policy.sql`,
  `mdm_create_instance.sql`

**Confirmed candidate already found, must be resolved here:** if Stage 8
(seed-universe) moves to after Stage 10 (dbt gold) under the early-data
phase running after deploy, dbt gold's INITIAL refresh (which happens at
`CREATE OR REPLACE DYNAMIC TABLE` time, per CLAUDE.md's dynamic-table
INITIAL-vs-scheduled-refresh distinction) would execute against an empty
`EDGARTOOLS_SOURCE` — Snowpipe won't have ingested anything yet, since
nothing has written new S3 objects. Determine:

1. Does an empty-source INITIAL refresh actually succeed (0 rows, no
   error) for every one of the 54 dbt gold models, or does any model's SQL
   assume non-empty input (e.g. a join that requires at least one row, a
   `dbt test` that isn't just a schema test)?
2. If it succeeds empty, does the dynamic table genuinely self-heal once
   Snowpipe + seed-universe (now running later) populate
   `EDGARTOOLS_SOURCE`, purely via the table's own `target_lag`-driven
   scheduled refresh — or does something in this pipeline (e.g. the
   standalone gold-refresh stage, 15) need to explicitly trigger a refresh
   for this to actually happen, and if so is that already covered by a
   later stage?
3. If either answer is unsafe, the fix is likely: early-data must precede
   deploy specifically for stage 10 (dbt gold) — i.e. a real phase-order
   exception, not just a labeling nuance. Say explicitly if that's the
   outcome, since it invalidates the clean 4-phase linear ordering this
   map's Destination currently assumes.

Also check every other flipped pair the final classification produces
(e.g. Stage 6 vs. Stage 7 reversing if 6=deploy and 7=provision — verify
neither direction has a real dependency) and report them even if all turn
out to be safe — a "checked N pairs, 0 conflicts beyond the known dbt-gold
one" result is itself the answer this ticket needs to produce.

## Answer

Checked every flipped pair the final classification (Ticket 01) produces.
**No real dependency breaks. The reorder is safe.**

### The flagged candidate: Stage 8 (seed-universe) moving after Stage 10 (dbt gold)

1. **`dbt test` surface, checked directly**: every schema test declared in
   `infra/snowflake/dbt/edgartools_gold/models/gold/gold.yml` is
   `not_null` (77 occurrences, confirmed via grep) — zero `unique`,
   `relationships`, `accepted_values`, or `dbt_utils`/row-count
   assertions anywhere in the gold model YAMLs. `not_null` is trivially
   satisfied by an empty table (nothing to violate). Separately, every
   `_*_unit_tests.yml` file uses dbt's `unit_tests:` feature, which runs
   model SQL against literal mock rows defined in the YAML itself —
   these never touch live Snowflake data at all, so they're entirely
   unaffected by whether `EDGARTOOLS_SOURCE` has real rows.
2. **Self-healing, confirmed by mechanism, not assumption**: a Snowflake
   dynamic table's INITIAL refresh (at `CREATE OR REPLACE`, which is what
   `dbt run` issues) can legitimately produce 0 rows if its source is
   empty — this is not an error condition. Once Stage 8 (now running
   before late-data, i.e. before Stage 15) writes new S3 objects,
   Snowpipe (already active since Stage 7 ran in provision) auto-ingests
   them into `EDGARTOOLS_SOURCE`; the downstream dynamic tables then pick
   up the new rows via their own `target_lag`-driven scheduled refresh —
   no manual `dbt run` re-trigger is required for data to flow through.
   Stage 15 ("Snowflake: standalone gold-refresh") explicitly triggers a
   refresh and then polls `gold-verify-live` for up to 20 attempts × 60s
   (20 minutes) before failing — this is deliberately fail-closed, so if
   the self-heal genuinely didn't happen in time, the install would stop
   with a clear error rather than silently shipping an empty gold layer.
3. **This risk is not actually new.** In the *current* (pre-reorder)
   order, Stage 8 already runs asynchronously ahead of Stage 10 with no
   explicit wait for Snowpipe ingestion to complete — Snowpipe latency is
   not instantaneous, so today's order provides no hard guarantee
   `EDGARTOOLS_SOURCE` is non-empty by the time `dbt run` executes either.
   The reorder doesn't introduce a new race; it just makes an
   already-existing race more likely to actually manifest (bigger gap),
   which the not_null-only test surface and Stage 15's fail-closed gate
   already tolerate.

**Conclusion**: no phase-order exception is needed for dbt gold. The
clean 4-phase linear order from Ticket 01 stands as-is; strike the
"if Ticket 02 found dbt gold needs early-data to precede it" contingency
language in Ticket 04 down to "verified not needed."

### Other flipped pairs (Stage 7, 13 moving earlier; Stage 5, 6 moving later)

- **Stage 7 (native-pull foundation, `deploy-snowflake-stack.sh`) vs.
  Stage 5/6 (ECR publish, ECS task defs)**: read `deploy-snowflake-stack.sh`
  directly — its only AWS-side touch is reading/writing the
  `dbt/snowflake` and `mdm/snowflake` Secrets Manager secrets (created
  empty by Stage 3, passive infrastructure) and creating
  `EDGARTOOLS_GOLD.SNOWFLAKE_RUN_MANIFEST_TASK`. Install.sh invokes it
  with `--run-validation`, not `--run-dbt`, so it does not itself call
  `dbt run` — no dependency on Stage 6's task definitions or Stage 5's
  ECR images in either direction.
- **Stage 13 (Postgres/graph prerequisites, `bootstrap-prod-mdm.sh`) vs.
  Stage 5/6/9/10/11/12**: read `bootstrap-prod-mdm.sh` directly — it only
  touches the `mdm/postgres_dsn` and `mdm/snowflake` Secrets Manager
  secrets and explicitly documents (its own comment, line 109) that it
  "never touches mdm/snowflake or reads dbt/snowflake" beyond what it
  needs. No reference to ECS task definitions, dbt run/test, or the
  loader role. Stage 9's MDM export target tables
  (`MDM_COMPANY_ENTITY` etc.) live in `EDGARTOOLS_GOLD`, not the `MDM`
  schema Stage 13 creates — no shared object between them.

No conflicts found beyond the one already analyzed above. Ticket 03/04 are
now unblocked to proceed with the Ticket 01 order as final.
