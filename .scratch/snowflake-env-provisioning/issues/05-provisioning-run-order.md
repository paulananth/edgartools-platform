# Decide end-to-end provisioning run order across source-native-pull → gold → MDM → Neo4j

Type: grilling
Status: resolved

## Question

Ticket 01 settled the Terraform structure (generated directory-per-account,
slug-identified) and Ticket 04 settled the AWS-side value contract this
structure's generated config depends on. What's still open is the actual
run order once a new environment's directory and config exist: which of the
four domains — source/native-pull (shares gold's Terraform root per the
map's Notes), gold (dbt), MDM (`bootstrap-prod-mdm.sh` generalized by
Ticket 03), Neo4j (Native App install, gated by Ticket 02's manual
Marketplace-terms step) — must run strictly before another, and which can
run in parallel?

Known hard constraints from the map's existing decisions:
- Neo4j's install (Ticket 02) requires a one-time, per-organization,
  ORGADMIN-only Snowsight step before any of its SQL/Terraform can run —
  this is a checkpoint the run order must pause at, not something that can
  be scripted around.
- Source/native-pull is the same Terraform root as gold (map Notes), so
  these two are not independently sequenceable — they land together.
- MDM's Postgres instance (`bootstrap-prod-mdm.sh`, per Ticket 03 now
  `--env-name <slug>`) and Neo4j's graph sync both read completed silver
  data conceptually, but need to be checked against whether they have a
  real data dependency on gold being live first, or just an operational
  convenience ordering (mirrors this repo's existing `load_history`
  Stage 2 MDM-after-Stage-1 pattern, per CLAUDE.md's Phased Pipeline
  section — worth checking whether that precedent actually applies to a
  brand-new, still-empty environment, or only to backfilling an existing
  one).

Resolve: produce the actual sequence (strict order vs. parallel-safe) for
a brand-new environment's four domains, including where the Ticket 02
manual checkpoint sits in that sequence.

## Answer

**The run order already exists — this isn't a design-from-scratch
question.** `infra/scripts/go-live.sh`'s `build_stages()` (`go-live.sh:601`)
defines a real, already-tested 13-stage sequential wizard, run one stage at
a time with per-stage operator confirmation (not parallel — it's a
human-gated sequential pipeline by construction, so "parallel vs. sequential"
resolves in favor of sequential, matching its existing design):

1. AWS: Terraform state bucket
2. AWS: passive infrastructure (VPC, S3, ECR, ECS cluster, etc.)
3. AWS: access roles/policies
4. AWS: ECR image publish (warehouse + MDM)
5. AWS: ECS task definitions and Step Functions
6. Snowflake: native-pull foundation (database/schemas/warehouses, storage integration — this is where source-native-pull and gold's shared Terraform root, per the map's Notes, actually lands)
7. Snowflake: dbt gold
8. Snowflake: Streamlit dashboard
9. Snowflake Postgres / graph prerequisites (MDM Postgres bootstrap + Neo4j grants — **see gap below**)
10. AWS: bronze_seed_silver_gold (one-click data refresh)
11. Snowflake: standalone gold-refresh
12. MDM + graph: connectivity, migrations, sync, verification (`mdm run` → `mdm sync-graph` → `mdm verify-graph`)
13. MDM + graph: AWS MDM E2E/status checks
14. Data: bounded smoke only

(AWS-side stages 1-5 are shown for completeness since they're part of
go-live.sh's real sequence — they remain this map's documented precondition,
not something this effort builds, per the map's Out-of-scope section.)

**Real gap this ticket surfaced:** stage 9 ("Snowflake Postgres / graph
prerequisites") runs `bootstrap-prod-mdm.sh` and then
`neo4j_graph_analytics_app_grants.sql` — but that SQL only *grants* against
the Neo4j Graph Analytics Native App; nothing in go-live.sh's stage list
ever actually **installs** it (`CREATE APPLICATION ... FROM LISTING`). Every
existing run of go-live.sh has silently depended on the app already being
installed out-of-band. For a genuinely brand-new account/org, that's not
true — Ticket 02 established that installation requires a one-time,
per-organization, ORGADMIN-only manual Marketplace-terms acceptance in
Snowsight before any install SQL can run at all.

**Fix: a new stage, "Snowflake: Neo4j Native App install," inserted early —
immediately after stage 1 (Terraform state bucket), before any other work.**
Rationale: the manual half (ORGADMIN clicking through Snowsight) is a
human-latency step of unknown duration. Placing it first means it's in
flight (or the operator is off doing it) while stages 2-8 — all of which are
independent of Neo4j — run to completion. By the time stage 9's grants step
is reached, the app is already installed and stage 9 just works, instead of
the wizard stalling mid-run waiting on a Snowsight tab. The new stage's
scripted half (`CREATE APPLICATION ... FROM LISTING`, once terms are
accepted) can run via `snow sql` or the `snowflake_execute` Terraform escape
hatch, per Ticket 02's findings — either is fine since this stage has no
downstream stage depending on *how* it was installed, only that it's
installed by stage 9.

**Not built here** — per wayfinder's plan-don't-do default, this records
the decision (adopt go-live.sh's existing order, insert the new stage after
stage 1); actually editing `go-live.sh` to add the stage and generalizing
its `--env`/`--snow-connection` flags per Ticket 03 is implementation work
for whoever executes this map's destination.

## Implementation (landed on `claude/snowflake-env-generator`)

New `infra/scripts/install-neo4j-graph-app.sh`, invoked by a new go-live.sh
stage inserted at **position 2**, immediately after "AWS: Terraform state
bucket" and well before the stage that GRANTs against the application (now
position 10). Verified by rendering the real plan, and pinned by
`test_neo4j_install_runs_early_and_before_the_grants_stage`.

Three things the decision left open that implementation had to settle:

1. **The listing global name is resolved at run time, not hardcoded.** Ticket
   02 surfaced a candidate (`GZTDZH40CN`) but flagged it explicitly unverified —
   transcribed from a URL embedded in a Snowflake guide rather than read off a
   `SHOW AVAILABLE LISTINGS` result. The script resolves the listing itself and
   reports ambiguity rather than silently taking the first hit; installing the
   wrong Native App is not something to guess at. `--listing-global-name`
   overrides when resolution is not possible. This also satisfies the map's
   standing "nothing should be hardcoded" constraint.
2. **The stage is idempotent.** It exits cleanly when the application already
   exists, checked *before* the permission-sensitive listing resolution — so
   re-running go-live.sh against an established environment is a no-op on the
   common path, not a failure.
3. **`BACKGROUND_INSTALL` is deliberately unused.** go-live.sh runs stages
   sequentially and the later grants stage needs the application to actually
   exist; a non-blocking install would just relocate the failure.

The unscriptable step is surfaced, not papered over: every failure path that
could be caused by the missing organization-level terms acceptance prints the
exact Snowsight navigation (ORGADMIN → Admin » Terms) and says plainly that
Snowflake documents no SQL or API equivalent.

Verified: `bash -n`; the argument guard; a `--dry-run` end-to-end; and all five
listing-resolution branches (single match, single match under a different
column casing, ambiguous, no matches, rows lacking a global name) exercised
against fixture payloads. 386 architecture tests pass, including 4 new ones for
this stage. **Not run against a live Snowflake account** — the install path
itself is unexercised, and the manual terms step means a genuinely new
organization cannot be fully validated without an operator.

### Correction: installing the app is necessary, but NOT sufficient

Recorded after implementation, because the Implementation section above (and
this ticket's original Answer) claimed more than is true.

Adding the install stage does **not** make the graph half of a brand-new
go-live work. `neo4j_graph_analytics_app_grants.sql` grants `USAGE`/`SELECT` on
`{{ database }}.NEO4J_GRAPH_MIGRATION`, but never creates that schema — it is
created by `mdm sync-graph` (`edgar_warehouse/mdm/snowflake_graph.py:1188`,
`CREATE SCHEMA IF NOT EXISTS`), which runs at **stage 13**, three stages *after*
the grants stage at **stage 10**. Verified live against the rendered plan and
the SQL file, not inferred.

On an established account this is invisible: the schema already exists from
prior runs. On a brand-new account the grants stage runs against a schema that
does not exist yet. This is the same failure class CLAUDE.md's dev go-live
blockers entry already records — applying the graph-review SQL to dev failed
with `GRAPH_ACTIVE_POINTER does not exist` because dev had never had a
generation-scoped sync, and the note there says the SQL "resumes cleanly once
dev gets a generation-scoped `sync-graph --generation-id ...` + `graph-activate`
run."

So the ordering gap is **grants-before-schema**, not merely
install-before-grants. This ticket only closed the latter. The former is
[Ticket 07](07-graph-grants-before-schema-ordering.md).
