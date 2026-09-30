"""Command registry for warehouse CLI operations."""

from __future__ import annotations

from edgar_warehouse.application.acquisition_command_registry import (
    registered_acquisition_handlers,
)
from edgar_warehouse.application.commands import (
    backfill_mdm_entity_ids,
    gold_refresh,
    verify_pipeline_run,
    write_run_summary,
)

LEGACY_COMMAND_REGISTRY = {
    "gold-refresh": gold_refresh.execute,
    "backfill-mdm-entity-ids": backfill_mdm_entity_ids.execute,
    "verify-pipeline-run": verify_pipeline_run.execute,
    "write-run-summary": write_run_summary.execute,
}

_REGISTERED_ACQUISITION_HANDLERS = registered_acquisition_handlers()
_DUPLICATE_COMMANDS = set(LEGACY_COMMAND_REGISTRY) & set(
    _REGISTERED_ACQUISITION_HANDLERS
)
if _DUPLICATE_COMMANDS:
    duplicate_names = ", ".join(sorted(_DUPLICATE_COMMANDS))
    raise ValueError(
        f"Commands registered in both acquisition and legacy registries: {duplicate_names}"
    )

COMMAND_REGISTRY = {
    **LEGACY_COMMAND_REGISTRY,
    **_REGISTERED_ACQUISITION_HANDLERS,
}
