# Decision: nothing is needed from codex/s3-retention-cleanup

Decided 2026-09-16, against `main` at `50d9a71d`.

**Verdict: do not apply. Conflicts resolve to "take `main`" on all 31 files.
Keep the patch as a historical artifact only.**

## The deciding fact: the work was never finished

The stash's orchestrator hunk imports, at two call sites:

    from edgar_warehouse.serving.targets.snowflake_direct import direct_publisher_from_env

`edgar_warehouse/serving/targets/snowflake_direct.py` does not exist on `main`
(`targets/` holds only `__init__.py`, `base.py`, `snowflake.py`) **and the
stash never adds it** — there is no `new file mode` entry for it anywhere in
the 5,720-line patch. Applying the stash in full therefore raises
`ImportError` on every gold-affecting command. This was mid-flight work when
it was stashed on 2026-08-01, not a complete change that merely went stale.

## Why the rest is superseded, not merely conflicted

| Check | Result |
|---|---|
| `SnowflakeDirectPublisher` on `main` | absent (0 hits) |
| `snowflake_direct_enabled` / `SNOWFLAKE_WRITER_SECRET_JSON` | absent (0 hits) |
| `SERVING_EXPORT_ROOT` (which the stash removes) | live in **18 files** |
| prod serving-export bucket | live: `edgartools-prod-snowflake-export-690839588395` |
| `native_pull` module (which the stash deletes) | referenced from **3** Terraform roots; all 5 files intact |
| manifest task / `LOAD_EXPORTS_FOR_RUN` | referenced by **12** files |
| `GOLD_AFFECTING_COMMANDS` (which the stash keys on) | renamed to `SOURCE_EXPORT_COMMANDS` (0 hits for the old name) |

The stash's own docstring asserts "the AWS runtime does not use this target; it
publishes through `SnowflakeDirectPublisher` and has no serving-export bucket."
Both halves of that are false on `main` today.

Two of the files referencing the manifest task — `13_silver_landing_ingest.sql`
and dbt's `silver_model_config.sql` macro — **postdate** this stash. The
platform's Snowflake ingestion evolved *through* native_pull (silver landing
zone + dbt collapse, per the silver-snowflake-migration and
dbt-gold-silver-rewiring maps), not away from it toward direct publication.

## The one candidate worth checking, and why it is also not needed

`edgar_warehouse/application/release_evidence.py` is the largest genuine
addition in the patch (+33/−16, net +17). It adds
`_REQUIRED_SNOWFLAKE_PUBLICATION_FIELDS` = (`run_id`, `business_date`,
`manifest_digest`, `load_status`, `refresh_status`) and a
`release_data_watermark.snowflake_publication` gate.

`main` already has the equivalent structure for the transport that actually
shipped: `_REQUIRED_WATERMARK_FIELDS`, `_REQUIRED_SNOWFLAKE_EXPORT_FIELDS`
(`run_id`, `business_date`, `manifest_digest`) and
`_REQUIRED_HOSTED_GRAPH_FIELDS` (`generation_id`, `publication_id`), wired into
the watermark validation at `release_evidence.py:1036-1130`. The stash's
version gates a publication path that does not exist. Nothing to port.

## Shape of the diff

`+587 / −3,284` across 81 files. Only three source files gain content
(`release_evidence.py` +17, `serving/targets/snowflake.py` +5,
`account_access/main.tf` +40); everything else is deletion of infrastructure
that is still running in production. It is a removal changeset for a cutover
that never happened.

## Recommended disposition

1. **Do not merge this branch.** It exists to preserve the patch, nothing else.
2. `stash@{1}` can be dropped — its content is durable here.
3. If direct Snowflake publication is ever revived, treat this as a design
   reference for the intent only, and start from current `main`. The missing
   `snowflake_direct.py` means there is no working implementation to recover.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014oAc1nXCnJEqHscRpK293F
