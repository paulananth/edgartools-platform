"""Structured runtime logging for MDM database and graph calls."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

_SQL_TABLE_RE = re.compile(
    r"\b(?:from|join|into|update|table)\s+([a-zA-Z_][a-zA-Z0-9_.$\"]*)",
    flags=re.IGNORECASE,
)


def emit_mdm_event(event: str, **payload: object) -> None:
    document = {
        "event": event,
        "emitted_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        **payload,
    }
    print(json.dumps(document, sort_keys=True, default=str), file=sys.stderr, flush=True)


def elapsed_ms(started_at: float | None) -> int | None:
    if started_at is None:
        return None
    return int((time.monotonic() - started_at) * 1000)


def install_mdm_sql_logging(engine: Engine) -> None:
    if os.environ.get("MDM_SQL_CALL_LOGGING", "true").strip().lower() in {"0", "false", "no"}:
        return
    if getattr(engine, "_edgar_mdm_sql_logging_installed", False):
        return
    setattr(engine, "_edgar_mdm_sql_logging_installed", True)

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        call_id = f"mdm-sql-{time.time_ns()}"
        context._edgar_mdm_sql_call_id = call_id
        context._edgar_mdm_sql_started_at = time.monotonic()
        emit_mdm_event(
            "mdm_sql_started",
            call_id=call_id,
            operation=_statement_operation(statement),
            parameter_count=_parameter_count(parameters),
            statement_hash=_statement_hash(statement),
            sql=_summarize_statement(statement),
            tables=_statement_tables(statement),
            executemany=bool(executemany),
        )

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        emit_mdm_event(
            "mdm_sql_completed",
            call_id=getattr(context, "_edgar_mdm_sql_call_id", None),
            duration_ms=elapsed_ms(getattr(context, "_edgar_mdm_sql_started_at", None)),
            operation=_statement_operation(statement),
            rowcount=getattr(cursor, "rowcount", None),
            statement_hash=_statement_hash(statement),
            tables=_statement_tables(statement),
            executemany=bool(executemany),
        )

    @event.listens_for(engine, "handle_error")
    def _handle_error(exception_context):  # noqa: ANN001
        context = exception_context.execution_context
        statement = exception_context.statement or ""
        emit_mdm_event(
            "mdm_sql_failed",
            call_id=getattr(context, "_edgar_mdm_sql_call_id", None) if context is not None else None,
            duration_ms=elapsed_ms(getattr(context, "_edgar_mdm_sql_started_at", None)) if context is not None else None,
            error=exception_context.original_exception.__class__.__name__,
            operation=_statement_operation(statement),
            statement_hash=_statement_hash(statement),
            tables=_statement_tables(statement),
        )


def _statement_hash(statement: str) -> str:
    normalized = _normalize_statement(statement)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _summarize_statement(statement: str, limit: int = 1000) -> str:
    normalized = _normalize_statement(statement)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _normalize_statement(statement: str) -> str:
    return " ".join(str(statement or "").split())


def _statement_operation(statement: str) -> str:
    normalized = _normalize_statement(statement)
    if not normalized:
        return "unknown"
    return normalized.split(" ", 1)[0].lower()


def _statement_tables(statement: str) -> list[str]:
    return sorted({_clean_identifier(match.group(1)) for match in _SQL_TABLE_RE.finditer(statement or "")})


def _clean_identifier(identifier: str) -> str:
    return identifier.strip('"').split(".")[-1].strip('"')


def _parameter_count(parameters: Any) -> int:
    if parameters is None:
        return 0
    if isinstance(parameters, dict):
        return len(parameters)
    if isinstance(parameters, (list, tuple)):
        if parameters and all(isinstance(item, dict) for item in parameters):
            return sum(len(item) for item in parameters)
        return len(parameters)
    return 1
