"""Shared command execution wrapper."""

from __future__ import annotations

import json
from typing import Any

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.application.command_context_factory import build_warehouse_context
from edgar_warehouse.application.errors import WarehouseRuntimeError


def execute_standard_command(command_name: str, args: Any) -> int:
    arguments = warehouse_orchestrator._namespace_to_payload(args)
    runtime_mode = "infrastructure_validation"
    try:
        context = build_warehouse_context(command_name)
        runtime_mode = context.runtime_mode
        payload = warehouse_orchestrator._execute_warehouse(
            context=context,
            command_name=command_name,
            arguments=arguments,
        )
    except WarehouseRuntimeError as exc:
        print(
            json.dumps(
                warehouse_orchestrator._error_payload(
                    command_name,
                    arguments,
                    str(exc),
                    runtime_mode=runtime_mode,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
