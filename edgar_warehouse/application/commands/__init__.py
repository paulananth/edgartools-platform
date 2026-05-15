"""Command registry for warehouse CLI operations."""

from __future__ import annotations

from edgar_warehouse.application.commands import (
    bootstrap_batch,
    bootstrap_full,
    bootstrap_next,
    bootstrap_recent_10,
    catch_up_daily_form_index,
    daily_incremental,
    full_reconcile,
    gold_refresh,
    load_daily_form_index_for_date,
    parse_ownership_bronze,
    seed_silver_batches,
    seed_universe,
    targeted_resync,
)

COMMAND_REGISTRY = {
    "bootstrap-full": bootstrap_full.execute,
    "bootstrap-recent-10": bootstrap_recent_10.execute,
    "daily-incremental": daily_incremental.execute,
    "load-daily-form-index-for-date": load_daily_form_index_for_date.execute,
    "catch-up-daily-form-index": catch_up_daily_form_index.execute,
    "targeted-resync": targeted_resync.execute,
    "full-reconcile": full_reconcile.execute,
    "seed-universe": seed_universe.execute,
    "seed-silver-batches": seed_silver_batches.execute,
    "parse-ownership-bronze": parse_ownership_bronze.execute,
    "bootstrap-batch": bootstrap_batch.execute,
    "bootstrap-next": bootstrap_next.execute,
    "gold-refresh": gold_refresh.execute,
}
