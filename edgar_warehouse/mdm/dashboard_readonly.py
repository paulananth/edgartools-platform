"""Read-only SQL helpers for the local MDM dashboard."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import (
    MdmCompany,
    MdmEntity,
    MdmEntityTypeDefinition,
    get_engine,
    get_session,
)


MDM_DATABASE_ENV_VAR = "MDM_DATABASE_URL"
MDM_UNAVAILABLE_MESSAGE = (
    "MDM database unavailable. Check `MDM_DATABASE_URL`, confirm the database "
    "is reachable, and restart the dashboard."
)


@dataclass(frozen=True)
class MdmDashboardStatus:
    connected: bool
    message: str
    env_var: str = MDM_DATABASE_ENV_VAR
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "message": self.message,
            "env_var": self.env_var,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class MdmSmokeResult:
    available: bool
    message: str
    limit: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    error_env_var: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "message": self.message,
            "limit": self.limit,
            "rows": list(self.rows),
            "error_env_var": self.error_env_var,
        }


def check_mdm_status(
    *,
    engine: Engine | None = None,
    session: Session | None = None,
) -> MdmDashboardStatus:
    owned_session: Session | None = None
    try:
        active_session = session
        if active_session is None:
            active_engine = engine or get_engine()
            owned_session = get_session(active_engine)
            active_session = owned_session

        entity_type_count = active_session.scalar(
            select(func.count(MdmEntityTypeDefinition.entity_type))
        )
        return MdmDashboardStatus(
            connected=True,
            message="MDM database connected.",
            details={"entity_types": int(entity_type_count or 0)},
        )
    except Exception:
        return _unavailable_status()
    finally:
        _close_owned_session(owned_session)


def run_mdm_smoke_query(
    *,
    engine: Engine | None = None,
    session: Session | None = None,
    limit: int = 5,
) -> MdmSmokeResult:
    row_limit = _bounded_limit(limit)
    owned_session: Session | None = None
    try:
        active_session = session
        if active_session is None:
            active_engine = engine or get_engine()
            owned_session = get_session(active_engine)
            active_session = owned_session

        stmt = (
            select(
                MdmEntity.entity_type,
                MdmCompany.cik,
                MdmCompany.canonical_name,
            )
            .join(MdmCompany, MdmCompany.entity_id == MdmEntity.entity_id)
            .order_by(MdmCompany.cik)
            .limit(row_limit)
        )
        rows = [
            {
                "entity_type": entity_type,
                "cik": int(cik),
                "canonical_name": canonical_name,
            }
            for entity_type, cik, canonical_name in active_session.execute(stmt)
        ]
        return MdmSmokeResult(
            available=True,
            message="MDM smoke query completed.",
            limit=row_limit,
            rows=rows,
        )
    except Exception:
        return _unavailable_smoke_result(row_limit)
    finally:
        _close_owned_session(owned_session)


def _bounded_limit(limit: int) -> int:
    try:
        requested = int(limit)
    except (TypeError, ValueError):
        requested = 5
    return max(0, min(requested, 5))


def _unavailable_status() -> MdmDashboardStatus:
    return MdmDashboardStatus(
        connected=False,
        message=MDM_UNAVAILABLE_MESSAGE,
        details={"check": "configuration"},
    )


def _unavailable_smoke_result(limit: int) -> MdmSmokeResult:
    return MdmSmokeResult(
        available=False,
        message=MDM_UNAVAILABLE_MESSAGE,
        limit=limit,
        rows=[],
        error_env_var=MDM_DATABASE_ENV_VAR,
    )


def _close_owned_session(session: Session | None) -> None:
    if session is None:
        return
    try:
        session.rollback()
    finally:
        session.close()
