"""Incremental registrations for SEC acquisition commands.

Registrations bind the three behaviors that must move together when a command
joins the warehouse runtime. Commands not present here continue through the
legacy registries and dispatch branches while migration proceeds one command at
a time.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.domain.policy.command_scope import parse_date
from edgar_warehouse.infrastructure.run_manifest_builder import planned_writes

if TYPE_CHECKING:
    from edgar_warehouse.infrastructure.object_storage import StorageLocation

ExecuteCommand = Callable[[Any], int]
ResolveCommandScope = Callable[..., dict[str, Any]]
PlanCommandWrites = Callable[..., dict[str, str]]


@dataclass(frozen=True)
class AcquisitionCommandRegistration:
    """Behaviors that define one acquisition command at the runtime seam."""

    name: str
    execute: ExecuteCommand
    resolve_scope: ResolveCommandScope
    planned_writes: PlanCommandWrites

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be empty")
        for behavior_name in ("execute", "resolve_scope", "planned_writes"):
            if not callable(getattr(self, behavior_name)):
                raise TypeError(f"{behavior_name} must be callable")


def _execute_load_daily_form_index_for_date(args: Any) -> int:
    # Import lazily: the existing command runner imports the orchestrator, which
    # in turn consults this registry for scope and write planning.
    from edgar_warehouse.application.commands.load_daily_form_index_for_date import (
        execute,
    )

    return execute(args)


def _resolve_load_daily_form_index_for_date_scope(
    *,
    arguments: dict[str, Any],
    now: datetime,
    silver_root: StorageLocation | None,
) -> dict[str, Any]:
    del now, silver_root
    target_date = parse_date(arguments.get("target_date"), "target_date")
    if target_date is None:
        raise WarehouseRuntimeError("target_date is required")
    return {"target_date": target_date.isoformat()}


def _plan_load_daily_form_index_for_date_writes(
    *,
    command_path: str,
    run_id: str,
    scope: dict[str, Any],
) -> dict[str, str]:
    return planned_writes(
        "load-daily-form-index-for-date",
        command_path,
        run_id,
        scope,
    )


def _execute_capture_filing_artifact(args: Any) -> int:
    # Import lazily: this command's own workflow imports the orchestrator,
    # which in turn consults this registry for scope and write planning.
    from edgar_warehouse.application.commands.capture_filing_artifact import execute

    return execute(args)


def _resolve_capture_filing_artifact_scope(
    *,
    arguments: dict[str, Any],
    now: datetime,
    silver_root: StorageLocation | None,
) -> dict[str, Any]:
    del now, silver_root
    candidate_id = str(arguments.get("candidate_id") or "").strip()
    if not candidate_id:
        raise WarehouseRuntimeError("candidate_id is required")
    return {"candidate_id": candidate_id}


def _plan_capture_filing_artifact_writes(
    *,
    command_path: str,
    run_id: str,
    scope: dict[str, Any],
) -> dict[str, str]:
    # Ticket 15 note: this declares the command's own run-manifest layers,
    # not the content-addressed Bronze Artifact the Facade writes -- that
    # key depends on the fetched payload's hash and is only known after the
    # network fetch completes, so it cannot be pre-declared here.
    return planned_writes(
        "capture-filing-artifact",
        command_path,
        run_id,
        scope,
    )


def _execute_drive_filing_discovery_for_date(args: Any) -> int:
    # Import lazily: this command's own workflow imports the orchestrator,
    # which in turn consults this registry for scope and write planning.
    from edgar_warehouse.application.commands.drive_filing_discovery_for_date import (
        execute,
    )

    return execute(args)


def _resolve_drive_filing_discovery_for_date_scope(
    *,
    arguments: dict[str, Any],
    now: datetime,
    silver_root: StorageLocation | None,
) -> dict[str, Any]:
    del now, silver_root
    target_date = parse_date(arguments.get("business_date"), "business_date")
    if target_date is None:
        raise WarehouseRuntimeError("business_date is required")
    return {"business_date": target_date.isoformat()}


def _plan_drive_filing_discovery_for_date_writes(
    *,
    command_path: str,
    run_id: str,
    scope: dict[str, Any],
) -> dict[str, str]:
    return planned_writes(
        "drive-filing-discovery-for-date",
        command_path,
        run_id,
        scope,
    )


def build_acquisition_command_registry(
    registrations: Iterable[AcquisitionCommandRegistration],
) -> dict[str, AcquisitionCommandRegistration]:
    """Build a validated immutable-by-convention command lookup."""

    registry: dict[str, AcquisitionCommandRegistration] = {}
    for registration in registrations:
        if registration.name in registry:
            raise ValueError(
                f"Duplicate acquisition command registration: {registration.name}"
            )
        registry[registration.name] = registration
    return registry


_ACQUISITION_COMMAND_REGISTRATIONS = build_acquisition_command_registry(
    (
        AcquisitionCommandRegistration(
            name="load-daily-form-index-for-date",
            execute=_execute_load_daily_form_index_for_date,
            resolve_scope=_resolve_load_daily_form_index_for_date_scope,
            planned_writes=_plan_load_daily_form_index_for_date_writes,
        ),
        AcquisitionCommandRegistration(
            name="capture-filing-artifact",
            execute=_execute_capture_filing_artifact,
            resolve_scope=_resolve_capture_filing_artifact_scope,
            planned_writes=_plan_capture_filing_artifact_writes,
        ),
        AcquisitionCommandRegistration(
            name="drive-filing-discovery-for-date",
            execute=_execute_drive_filing_discovery_for_date,
            resolve_scope=_resolve_drive_filing_discovery_for_date_scope,
            planned_writes=_plan_drive_filing_discovery_for_date_writes,
        ),
    )
)


def acquisition_command_registration(
    command_name: str,
) -> AcquisitionCommandRegistration | None:
    """Return a migrated acquisition registration, if one exists."""

    return _ACQUISITION_COMMAND_REGISTRATIONS.get(command_name)


def registered_acquisition_handlers() -> dict[str, ExecuteCommand]:
    """Return the command-router handlers supplied by migrated registrations."""

    return {
        command_name: registration.execute
        for command_name, registration in _ACQUISITION_COMMAND_REGISTRATIONS.items()
    }
