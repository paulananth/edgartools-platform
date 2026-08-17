# 06 — Repoint the Orphan Evidence-Table Exports at Snowflake Silver Directly

**What to build:** Five `gold_models.py` Python builders have no dbt gold
model at all today — `sec_subsidiary_evidence`, `sec_auditor_report_evidence`,
`sec_employment_event`, `sec_adv_firm_roster`, and `sec_adv_private_fund`
(the passthrough export, distinct from the dimensional `private_funds` table
in Ticket 04) — they write straight into `EDGARTOOLS_SOURCE` with nothing
downstream consuming them via dbt `ref()`. Since there's no dbt cutover path
for tables nothing `ref()`s, this ticket repoints each export's read from
local DuckDB to Snowflake silver directly, independent of the dbt-facing
batches in Tickets 02-05.

**Blocked by:** None — can start immediately, independent of Tickets 02-05

**Status:** resolved — all 5 builders repointed at Snowflake and
unit-tested; the cutover validation standard's real-scale, real-data leg is
deferred for the same account-mismatch reason Tickets 03/04 documented.

- [x] All 5 exports read from Snowflake silver instead of local DuckDB
- [~] Output row content matches today's DuckDB-backed export per the
      cutover validation standard — column-for-column parity with the old
      DuckDB SQL confirmed by inspection (same table/column names, same
      target `pa.Schema` constants) and pinned by rewritten unit tests with
      real row content (including NULL handling), but not verified against
      live prod data end-to-end (see "Verification performed, and its
      limit" below).
- [~] No behavior change for any downstream consumer of these 5
      `EDGARTOOLS_SOURCE` tables — true for the 5 tables' own consumers: the
      write path (Parquet export + Snowflake native-pull ingest into
      `EDGARTOOLS_SOURCE`) is completely unchanged, only the read source
      changed, same `pa.Schema` constants, same
      `SNOWFLAKE_EXPORT_TABLES`/`GOLD_EXPORT_MAP` registrations (confirmed
      unchanged by the existing registry tests, still passing unmodified).
      Downgraded from `[x]` after the code-review pass (Standards + Spec
      axes both independently flagged the same real gap): this ticket puts
      *every* gold-affecting command's build_gold()/iter_gold_tables() pass
      behind a live Snowflake connection for the first time — previously
      only these 5 tables' own DuckDB reads could fail, now a Snowflake
      outage or a missing secret fails the entire ~24-table gold build,
      including the 19 tables that never touch Snowflake to build. Mitigated,
      not eliminated, by the deploy-script fix below: without it, a
      freshly-provisioned environment missing the MDM Snowflake secret would
      have deployed successfully and only failed later, deep inside
      `build_gold()`.

## Answer

**All 5 builders repointed**, in `edgar_warehouse/serving/gold_models.py`:
`_build_sec_subsidiary_evidence`, `_build_sec_auditor_report_evidence`,
`_build_sec_employment_event`, `_build_sec_adv_firm_roster`, and
`_build_sec_adv_private_fund_passthrough` no longer take the local DuckDB
`conn` threaded through every other builder in `_gold_table_builders()` —
each now calls a new helper, `_fetch_snowflake_silver_rows(query)`, that
opens its own `snowflake-connector-python` connection scoped to
`EDGARTOOLS_SILVER`, runs the query, and returns lowercased-column row
dicts (Snowflake returns uppercase names for unquoted identifiers by
default). Each builder then applies the exact same per-field
`_coerce_int`/`_coerce_float`/`_coerce_date` coercion already established by
this file's other Python-side builders (`_build_fact_adv_office`,
`_build_fact_adv_disclosure`, `_build_fact_adv_private_fund` —
`_fetch_rows`/`_table_from_records` pattern), explicit-sorts the resulting
records to reproduce the old SQL's `ORDER BY`, and returns
`_table_from_records(schema, records)` against the same
`_SEC_*_SCHEMA`/`_FACT_*_SCHEMA` constants as before — output shape is
byte-identical to the old DuckDB path; only where the rows come from
changed.

**New shared connection helper**: `silver_connection_settings()`, added to
`edgar_warehouse/mdm/export.py` (next to `SnowflakeConnectionSettings`) —
`SnowflakeConnectionSettings.from_env()` with its schema overridden to
`DBT_SILVER_SCHEMA`/`EDGARTOOLS_SILVER`. This is not new plumbing:
`mdm_entity_backfill.py`'s Phase B sweep already had an identical private
`_silver_connection_settings()` doing the same thing — promoted it to a
shared public function rather than writing a second near-duplicate for
gold_models.py to call, and updated `mdm_entity_backfill.py`'s own private
wrapper to delegate to it (a real, small "Duplicated Code" smell that would
otherwise have existed twice after this ticket; fixed at the point it was
about to be introduced, not left for a later pass).

**Deployment prerequisite already satisfied, not new work**: these 5
builders need `MDM_SNOWFLAKE_SECRET_JSON` (the same secret
`SnowflakeConnectionSettings.from_env()` reads) present in the warehouse
ECS task's environment. Checked `infra/scripts/deploy-aws-application.sh`
(`write_container_definitions`, ~line 1150-1157): this secret is already
injected into every warehouse task definition today — added for
`backfill-mdm-entity-ids` (mdm-ahead-of-silver map, Phase B), which needs
the identical `SnowflakeConnectionSettings.from_env()` connection. Since
`gold-refresh`/`daily_incremental`/`bootstrap`/etc. all run on that same
warehouse task family, no deploy-script change is needed for this ticket —
the credential is already wired wherever `iter_gold_tables()`/`build_gold()`
run in prod.

**Tests**: rewrote `tests/unit/test_agent_evidence_gold_export.py` and
`tests/unit/test_adv_firm_roster_gold_export.py` (previously built an
in-memory DuckDB fixture and called the builders with `conn` — no longer
applicable, since these builders take no arguments now) to instead patch
`edgar_warehouse.mdm.export.silver_connection_settings` with a new shared
test double, `tests/unit/_fake_snowflake.py`
(`FakeSnowflakeConnection`/`FakeSnowflakeCursor`/
`FakeSnowflakeConnectionSettings` — a minimal in-memory stand-in for
`snowflake-connector-python`'s connection/cursor shape, dispatching fixture
rows by matching the queried table name in the SQL text). Row-content
fixtures reproduce the exact same rows the old DuckDB tests inserted
(including `NULL`s, e.g. `sec_employment_event`'s `previous_role`/
`compensation_amount`), so both files still assert real per-field output
content, not just row counts. Also updated 4 call sites in
`tests/unit/test_validate_data_quality.py` (which exercises `build_gold()`
indirectly via `validate_data_quality()`) and 3 in
`tests/unit/test_gold_models_streaming.py` (which iterates/materializes the
*entire* builder set, including these 5) with the same patch — both were
silently exercising the old DuckDB `conn` path for these 5 tables and would
otherwise have attempted a real Snowflake connection on every test run.
Full suite green: 2171 passed, 4 skipped (identical count to before this
ticket — no test functions added or removed, only rewired).

**Code-review pass (Standards + Spec axes):** both axes independently
converged on the same real, most-severe finding — this ticket makes
`MDM_SNOWFLAKE_SECRET_JSON` a hard runtime dependency for the *entire* gold
build (all ~24 tables), but `infra/scripts/deploy-aws-application.sh` only
enforced that secret's presence when `--enable-mdm` was passed
(`MDM_DEPLOYMENT_MODE=enabled`, ~line 846-850); a warehouse-only deploy
without that flag would previously pass with the secret silently absent
and only fail later, deep inside `build_gold()`, on the first of these 5
builders. In practice `MDM_SNOWFLAKE_SECRET_ARN` auto-resolves from
Secrets Manager by fixed name (`${NAME_PREFIX}/mdm/snowflake`, ~line
764-766) regardless of `--enable-mdm`, so an already-MDM-bootstrapped
environment (prod, post-Phase-B) was never actually exposed — but a
freshly-provisioned environment that hasn't yet run
`bootstrap-aws-mdm-secrets.sh` (exactly the situation the concurrent
`snowflake-env-provisioning` effort is in) genuinely would have been.
**Fixed**: added an unconditional fail-closed check for
`MDM_SNOWFLAKE_SECRET_ARN` in the same pre-flight block as the script's
other required-ARN checks (`EDGAR_IDENTITY_SECRET_ARN`,
`EXECUTION_ROLE_ARN`, etc., ~line 815-822), and removed the now-dead
conditional check for it inside the `--enable-mdm` branch (it can no
longer be empty by the time that branch runs). `bash -n` confirms the
script still parses. Not covered by a new automated test — no existing
test exercises this script's bash pre-flight `is_empty ... && fail` guards
at all (checked: `tests/architecture/test_aws_application_deploy.py` only
tests the generated JSON/ASL shape, not these guards), so this matches the
existing coverage level for every sibling check in that block rather than
introducing new test infrastructure disproportionate to this ticket.

Two secondary, lower-severity points raised by the reviews were considered
and deliberately left as-is, not silently missed:
- **5 separate Snowflake connections per gold build** (one per orphan
  builder) instead of reusing one connection the way
  `mdm_entity_backfill.py`'s sweep does — a real deviation from that
  precedent, but gold-refresh runs on a schedule, not in a hot loop; 5
  extra TLS/auth round-trips (roughly seconds, not a resource concern) is a
  reasonable trade for keeping each builder self-contained and independently
  connection-scoped rather than threading a shared, lazily-opened
  connection through `_gold_table_builders()` with no natural teardown
  point in a streaming generator.
- **Duplicated column-name lists** across the two rewritten test files
  (`_fake_snowflake.py`'s fixtures) — real but minor test-only duplication;
  consolidating them would add cross-file test coupling for marginal
  benefit.

**Verification performed, and its limit:** everything above is
structurally verified (schema conformance, per-field coercion parity with
the old SQL's `CAST`s, `ORDER BY` parity via explicit Python sorts, real row
content including `NULL`s) via unit tests against a fake Snowflake
connection — genuinely useful, account-agnostic confirmation that the SQL
text, column mapping, and coercion logic are correct. **Not verified**: an
end-to-end run against real prod `EDGARTOOLS_SILVER` data, because
`edgartools-prod`/`snowconn` in this session's `~/.snowflake/connections.toml`
still resolve to the freshly-provisioned, empty account documented in
Tickets 03/04's Answers (`PRJEDJU`/`QJB05385`, not `XCPCLKF`/`KB19989`) —
the same `snowflake-env-provisioning` blocker, not a new one. Once that
account is restored/reprovisioned, whoever picks this up should: (1) run
`gold-refresh` (or trigger `iter_gold_tables()` directly) against real prod
data and confirm each of these 5 tables' row counts and a content sample
match what the previous DuckDB-backed run produced for the same silver
snapshot, (2) since this ticket's new read path and old read path are not
simultaneously present in `EDGARTOOLS_SOURCE` the way Tickets 02-04's dbt
`ref()` cutover left an old-vs-new comparison target, the practical
before/after check is: snapshot `EDGARTOOLS_SOURCE`'s row counts for these
5 tables immediately before deploying this change, redeploy, re-run the
gold-affecting command, and diff — not a `HASH_AGG` SQL script comparison
like `ticket02_gold_silver_cutover_reconciliation.sql` (there is no second,
still-live sourcing path in Snowflake to diff against for these 5 tables,
unlike Tickets 02-04's dbt-silver-vs-EDGARTOOLS_SOURCE-mirror comparison).
