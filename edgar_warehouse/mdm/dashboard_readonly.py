"""Read-only SQL helpers for the local MDM dashboard."""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Mapping

from sqlalchemy import case, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import (
    MdmAdviser,
    MdmCompany,
    MdmEntity,
    MdmEntityTypeDefinition,
    MdmFund,
    MdmPerson,
    MdmRelationshipInstance,
    MdmRelationshipType,
    MdmSecurity,
    get_engine,
    get_session,
)


MDM_DATABASE_ENV_VAR = "MDM_DATABASE_URL"
MDM_UNAVAILABLE_MESSAGE = (
    "MDM database unavailable. Check `MDM_DATABASE_URL`, confirm the database "
    "is reachable, and restart the dashboard."
)
ENTITY_DOMAIN_ORDER = ("company", "adviser", "person", "security", "fund")
ENTITY_DOMAIN_LABELS = {
    "company": "Companies",
    "adviser": "Advisers",
    "person": "People",
    "security": "Securities",
    "fund": "Funds",
}
ENTITY_DOMAIN_MODELS = {
    "company": MdmCompany,
    "adviser": MdmAdviser,
    "person": MdmPerson,
    "security": MdmSecurity,
    "fund": MdmFund,
}


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


@dataclass(frozen=True)
class MdmMetricWarning:
    severity: str
    message: str
    action: str
    group: str = "mdm"

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "message": self.message,
            "action": self.action,
            "group": self.group,
        }


@dataclass(frozen=True)
class MdmEntityMetric:
    domain: str
    label: str
    count: int
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "label": self.label,
            "count": self.count,
            "status": self.status,
        }


@dataclass(frozen=True)
class MdmRelationshipMetric:
    relationship_type: str
    active_count: int
    pending_graph_sync_count: int
    total_count: int
    status: str
    source_node_type: str | None = None
    target_node_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "relationship_type": self.relationship_type,
            "active_count": self.active_count,
            "pending_graph_sync_count": self.pending_graph_sync_count,
            "total_count": self.total_count,
            "status": self.status,
            "source_node_type": self.source_node_type,
            "target_node_type": self.target_node_type,
        }


@dataclass(frozen=True)
class MdmDiagnosticSample:
    relationship_type: str
    source_entity_id: str
    source_entity_name: str | None
    target_entity_id: str
    target_entity_name: str | None
    created_at: str | None
    mdm_edge_key: tuple[str, str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "relationship_type": self.relationship_type,
            "source_entity_id": self.source_entity_id,
            "source_entity_name": self.source_entity_name,
            "target_entity_id": self.target_entity_id,
            "target_entity_name": self.target_entity_name,
            "created_at": self.created_at,
            "mdm_edge_key": self.mdm_edge_key,
        }


@dataclass(frozen=True)
class MdmRelationshipDiagnosticInputs:
    available: bool
    message: str
    candidate_rows: list[MdmDiagnosticSample] = field(default_factory=list)
    known_mdm_edge_keys: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    active_relationship_counts: dict[str, int] = field(default_factory=dict)
    last_refreshed: str | None = None
    error_env_var: str | None = None
    warnings: list[MdmMetricWarning] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "message": self.message,
            "candidate_rows": [row.as_dict() for row in self.candidate_rows],
            "known_mdm_edge_keys": {
                key: list(value) for key, value in self.known_mdm_edge_keys.items()
            },
            "active_relationship_counts": dict(self.active_relationship_counts),
            "last_refreshed": self.last_refreshed,
            "error_env_var": self.error_env_var,
            "warnings": [warning.as_dict() for warning in self.warnings],
        }


@dataclass(frozen=True)
class RelationshipCoverageMetric:
    relationship_type: str
    mdm_active_count: int
    pending_graph_sync_count: int
    synced_count: int
    coverage_percent: float | None
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "relationship_type": self.relationship_type,
            "mdm_active_count": self.mdm_active_count,
            "pending_graph_sync_count": self.pending_graph_sync_count,
            "synced_count": self.synced_count,
            "coverage_percent": self.coverage_percent,
            "status": self.status,
        }


@dataclass(frozen=True)
class MdmDashboardMetrics:
    available: bool
    message: str
    entity_counts: dict[str, MdmEntityMetric] = field(default_factory=dict)
    relationship_counts: dict[str, MdmRelationshipMetric] = field(default_factory=dict)
    pending_sync_samples: list[MdmDiagnosticSample] = field(default_factory=list)
    warnings: list[MdmMetricWarning] = field(default_factory=list)
    registry: dict[str, Any] = field(default_factory=dict)
    last_refreshed: str | None = None
    error_env_var: str | None = None
    # 07-03 (RSYNC-01/03): the primary publication-freshness signal, from the
    # transactional mdm_publication_request queue (edgar_warehouse.mdm.publication).
    # relationship_counts.pending_graph_sync_count / pending_sync_samples above
    # remain as secondary, per-row diagnostics -- not replaced.
    publication_health: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "message": self.message,
            "entity_counts": {
                key: metric.as_dict() for key, metric in self.entity_counts.items()
            },
            "relationship_counts": {
                key: metric.as_dict() for key, metric in self.relationship_counts.items()
            },
            "pending_sync_samples": [
                sample.as_dict() for sample in self.pending_sync_samples
            ],
            "warnings": [warning.as_dict() for warning in self.warnings],
            "registry": dict(self.registry),
            "last_refreshed": self.last_refreshed,
            "error_env_var": self.error_env_var,
            "publication_health": dict(self.publication_health),
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


def get_mdm_dashboard_metrics(
    *,
    engine: Engine | None = None,
    session: Session | None = None,
    per_type_sample_limit: int = 5,
    global_sample_limit: int = 50,
) -> MdmDashboardMetrics:
    sample_limit = _bounded_sample_limit(per_type_sample_limit, default=5, maximum=50)
    total_limit = _bounded_sample_limit(global_sample_limit, default=50, maximum=500)
    owned_session: Session | None = None
    try:
        active_session = session
        if active_session is None:
            active_engine = engine or get_engine()
            owned_session = get_session(active_engine)
            active_session = owned_session

        entity_counts = _get_entity_counts(active_session)
        relationship_counts = _get_relationship_counts(active_session)
        pending_samples = _get_relationship_samples(
            active_session,
            pending_only=True,
            per_type_sample_limit=sample_limit,
            global_sample_limit=total_limit,
        )
        publication_health = _get_publication_health(active_session)
        warnings = _build_mdm_warnings(entity_counts, relationship_counts, publication_health)
        registry = _get_registry_details(active_session)
        return MdmDashboardMetrics(
            available=True,
            message="MDM dashboard metrics loaded.",
            entity_counts=entity_counts,
            relationship_counts=relationship_counts,
            pending_sync_samples=pending_samples,
            warnings=warnings,
            registry=registry,
            last_refreshed=_utc_now_iso(),
            publication_health=publication_health,
        )
    except Exception:
        return _unavailable_metrics()
    finally:
        _close_owned_session(owned_session)


def get_active_relationship_diagnostic_inputs(
    *,
    engine: Engine | None = None,
    session: Session | None = None,
    per_type_sample_limit: int = 5,
    global_sample_limit: int = 50,
) -> MdmRelationshipDiagnosticInputs:
    sample_limit = _bounded_sample_limit(per_type_sample_limit, default=5, maximum=50)
    total_limit = _bounded_sample_limit(global_sample_limit, default=50, maximum=500)
    owned_session: Session | None = None
    try:
        active_session = session
        if active_session is None:
            active_engine = engine or get_engine()
            owned_session = get_session(active_engine)
            active_session = owned_session

        candidate_rows = _get_relationship_samples(
            active_session,
            pending_only=False,
            per_type_sample_limit=sample_limit,
            global_sample_limit=total_limit,
        )
        known_mdm_edge_keys: dict[str, list[tuple[str, str, str]]] = {}
        for row in candidate_rows:
            known_mdm_edge_keys.setdefault(row.relationship_type, []).append(
                row.mdm_edge_key
            )
        relationship_counts = _get_relationship_counts(active_session)
        return MdmRelationshipDiagnosticInputs(
            available=True,
            message="MDM relationship diagnostic inputs loaded.",
            candidate_rows=candidate_rows,
            known_mdm_edge_keys=known_mdm_edge_keys,
            active_relationship_counts={
                relationship_type: metric.active_count
                for relationship_type, metric in relationship_counts.items()
            },
            last_refreshed=_utc_now_iso(),
        )
    except Exception:
        return MdmRelationshipDiagnosticInputs(
            available=False,
            message=MDM_UNAVAILABLE_MESSAGE,
            candidate_rows=[],
            known_mdm_edge_keys={},
            active_relationship_counts={},
            error_env_var=MDM_DATABASE_ENV_VAR,
            warnings=[_unavailable_warning()],
        )
    finally:
        _close_owned_session(owned_session)


def build_relationship_coverage_rows(
    mdm_relationships: Mapping[str, Mapping[str, Any]],
) -> list[RelationshipCoverageMetric]:
    rows: list[RelationshipCoverageMetric] = []
    for relationship_type in sorted(mdm_relationships):
        mdm_payload = mdm_relationships.get(relationship_type, {})
        mdm_active_count = _int_value(mdm_payload.get("active_count"))
        pending_graph_sync_count = _int_value(
            mdm_payload.get("pending_graph_sync_count")
        )
        synced_count = max(mdm_active_count - pending_graph_sync_count, 0)
        if mdm_active_count > 0:
            coverage_percent = round(synced_count / mdm_active_count * 100, 2)
        else:
            coverage_percent = None
        if mdm_active_count == 0:
            status = "No active MDM rows"
        elif pending_graph_sync_count > 0:
            status = "Pending sync"
        else:
            status = "OK"
        rows.append(
            RelationshipCoverageMetric(
                relationship_type=relationship_type,
                mdm_active_count=mdm_active_count,
                pending_graph_sync_count=pending_graph_sync_count,
                synced_count=synced_count,
                coverage_percent=coverage_percent,
                status=status,
            )
        )
    return rows


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


def _bounded_sample_limit(limit: int, *, default: int, maximum: int) -> int:
    try:
        requested = int(limit)
    except (TypeError, ValueError):
        requested = default
    return max(0, min(requested, maximum))


def _get_entity_counts(session: Session) -> dict[str, MdmEntityMetric]:
    counts: dict[str, MdmEntityMetric] = {}
    for domain in ENTITY_DOMAIN_ORDER:
        count = int(session.scalar(select(func.count()).select_from(ENTITY_DOMAIN_MODELS[domain])) or 0)
        status = "OK" if count > 0 else "No rows"
        counts[domain] = MdmEntityMetric(
            domain=domain,
            label=ENTITY_DOMAIN_LABELS[domain],
            count=count,
            status=status,
        )
    return counts


def _get_relationship_counts(session: Session) -> dict[str, MdmRelationshipMetric]:
    pending_expr = case(
        (
            (MdmRelationshipInstance.instance_id.isnot(None))
            & (MdmRelationshipInstance.graph_synced_at.is_(None)),
            1,
        ),
        else_=0,
    )
    rows = session.execute(
        select(
            MdmRelationshipType.rel_type_name,
            MdmRelationshipType.source_node_type,
            MdmRelationshipType.target_node_type,
            func.count(MdmRelationshipInstance.instance_id),
            func.coalesce(func.sum(pending_expr), 0),
        )
        .outerjoin(
            MdmRelationshipInstance,
            (MdmRelationshipInstance.rel_type_id == MdmRelationshipType.rel_type_id)
            & (MdmRelationshipInstance.is_active.is_(True)),
        )
        .where(MdmRelationshipType.is_active.is_(True))
        .group_by(
            MdmRelationshipType.rel_type_name,
            MdmRelationshipType.source_node_type,
            MdmRelationshipType.target_node_type,
        )
        .order_by(MdmRelationshipType.rel_type_name)
    )
    metrics: dict[str, MdmRelationshipMetric] = {}
    for rel_type_name, source_type, target_type, active_count, pending_count in rows:
        active_total = int(active_count or 0)
        pending_total = int(pending_count or 0)
        if pending_total > 0:
            status = "Pending sync"
        elif active_total == 0:
            status = "No active MDM rows"
        else:
            status = "OK"
        metrics[str(rel_type_name)] = MdmRelationshipMetric(
            relationship_type=str(rel_type_name),
            active_count=active_total,
            pending_graph_sync_count=pending_total,
            total_count=active_total,
            status=status,
            source_node_type=source_type,
            target_node_type=target_type,
        )
    return metrics


def _get_relationship_samples(
    session: Session,
    *,
    pending_only: bool,
    per_type_sample_limit: int,
    global_sample_limit: int,
) -> list[MdmDiagnosticSample]:
    if per_type_sample_limit <= 0 or global_sample_limit <= 0:
        return []
    samples: list[MdmDiagnosticSample] = []
    rel_types = session.execute(
        select(MdmRelationshipType.rel_type_id, MdmRelationshipType.rel_type_name)
        .where(MdmRelationshipType.is_active.is_(True))
        .order_by(MdmRelationshipType.rel_type_name)
    ).all()
    for rel_type_id, rel_type_name in rel_types:
        if len(samples) >= global_sample_limit:
            break
        remaining = global_sample_limit - len(samples)
        row_limit = min(per_type_sample_limit, remaining)
        predicates = [
            MdmRelationshipInstance.rel_type_id == rel_type_id,
            MdmRelationshipInstance.is_active.is_(True),
        ]
        if pending_only:
            predicates.append(MdmRelationshipInstance.graph_synced_at.is_(None))
        rows = session.execute(
            select(
                MdmRelationshipInstance.source_entity_id,
                MdmRelationshipInstance.target_entity_id,
                MdmRelationshipInstance.created_at,
            )
            .where(*predicates)
            .order_by(
                MdmRelationshipInstance.created_at,
                MdmRelationshipInstance.instance_id,
            )
            .limit(row_limit)
        ).all()
        entity_names = _get_entity_names(
            session,
            [entity_id for row in rows for entity_id in (row[0], row[1])],
        )
        for source_entity_id, target_entity_id, created_at in rows:
            source_id = str(source_entity_id)
            target_id = str(target_entity_id)
            rel_name = str(rel_type_name)
            samples.append(
                MdmDiagnosticSample(
                    relationship_type=rel_name,
                    source_entity_id=source_id,
                    source_entity_name=entity_names.get(source_id, source_id),
                    target_entity_id=target_id,
                    target_entity_name=entity_names.get(target_id, target_id),
                    created_at=_format_timestamp(created_at),
                    mdm_edge_key=(rel_name, source_id, target_id),
                )
            )
    return samples


def _get_entity_names(session: Session, entity_ids: list[Any]) -> dict[str, str]:
    wanted_ids = {str(entity_id) for entity_id in entity_ids if entity_id is not None}
    if not wanted_ids:
        return {}
    names: dict[str, str] = {}
    name_queries = (
        select(MdmCompany.entity_id, MdmCompany.canonical_name),
        select(MdmAdviser.entity_id, MdmAdviser.canonical_name),
        select(MdmPerson.entity_id, MdmPerson.canonical_name),
        select(MdmSecurity.entity_id, MdmSecurity.canonical_title),
        select(MdmFund.entity_id, MdmFund.canonical_name),
    )
    for stmt in name_queries:
        for entity_id, display_name in session.execute(stmt):
            entity_key = str(entity_id)
            if entity_key in wanted_ids:
                names[entity_key] = str(display_name)
    return names


def _get_registry_details(session: Session) -> dict[str, Any]:
    entity_type_rows = [
        {"entity_type": str(entity_type), "neo4j_label": str(neo4j_label)}
        for entity_type, neo4j_label in session.execute(
            select(
                MdmEntityTypeDefinition.entity_type,
                MdmEntityTypeDefinition.neo4j_label,
            )
            .where(MdmEntityTypeDefinition.is_active.is_(True))
            .order_by(MdmEntityTypeDefinition.entity_type)
        )
    ]
    entity_types = [row["entity_type"] for row in entity_type_rows]
    relationship_types = [
        row[0]
        for row in session.execute(
            select(MdmRelationshipType.rel_type_name)
            .where(MdmRelationshipType.is_active.is_(True))
            .order_by(MdmRelationshipType.rel_type_name)
        )
    ]
    return {
        "entity_types": entity_types,
        "entity_type_details": entity_type_rows,
        "relationship_types": relationship_types,
    }


def _get_publication_health(session: Session) -> dict[str, Any]:
    """07-03: primary publication-freshness signal.

    Degrades to an "unknown" status (rather than raising) when the
    mdm_publication_request table is absent -- e.g. an environment that
    hasn't run `mdm migrate` since this plan landed -- so a missing new
    table doesn't take down the rest of the dashboard's existing metrics.
    """
    try:
        from edgar_warehouse.mdm.publication import compute_publication_freshness

        return compute_publication_freshness(session).as_dict()
    except Exception:
        return {
            "status": "unknown",
            "oldest_pending_age_seconds": None,
            "oldest_pending_request_id": None,
            "is_backfill_exempt": False,
            "backfill_deadline_expired": False,
            "lifecycle_counts": {},
        }


def _build_mdm_warnings(
    entity_counts: Mapping[str, MdmEntityMetric],
    relationship_counts: Mapping[str, MdmRelationshipMetric],
    publication_health: Mapping[str, Any] | None = None,
) -> list[MdmMetricWarning]:
    warnings: list[MdmMetricWarning] = []
    zero_domains = [
        metric.label for metric in entity_counts.values() if metric.count == 0
    ]
    if zero_domains:
        warnings.append(
            MdmMetricWarning(
                severity="info",
                message=f"No MDM rows found for: {', '.join(zero_domains)}.",
                action="Confirm source coverage if these domains should be populated.",
            )
        )
    pending_total = sum(
        metric.pending_graph_sync_count for metric in relationship_counts.values()
    )
    if pending_total > 0:
        warnings.append(
            MdmMetricWarning(
                severity="warning",
                message=f"{pending_total} active MDM relationships are pending graph sync.",
                action="Review graph sync status or run the existing MDM graph sync workflow.",
                group="graph_sync",
            )
        )
    if not relationship_counts:
        warnings.append(
            MdmMetricWarning(
                severity="warning",
                message="No active MDM relationship types are registered.",
                action="Check MDM relationship registry migrations and seed data.",
            )
        )
    warnings.extend(_publication_health_warnings(publication_health or {}))
    return warnings


def _publication_health_warnings(publication_health: Mapping[str, Any]) -> list[MdmMetricWarning]:
    status = publication_health.get("status")
    age = publication_health.get("oldest_pending_age_seconds")
    if status == "warning":
        warnings = [MdmMetricWarning(
            severity="warning",
            message=f"Publication queue freshness warning: oldest pending request is {age:.0f}s old (>=5min).",
            action="Confirm the publication coordinator is running (mdm publication-claim).",
            group="publication_freshness",
        )]
    elif status == "hard_alert":
        if publication_health.get("backfill_deadline_expired"):
            message = "Publication queue hard alert: a declared backfill window's deadline has passed."
            action = "Investigate the overdue backfill request or extend/replace its deadline."
        else:
            message = f"Publication queue hard alert: oldest pending request is {age:.0f}s old (>=15min)."
            action = "Investigate the publication coordinator/worker immediately -- graph data is stale."
        warnings = [MdmMetricWarning(
            severity="error", message=message, action=action, group="publication_freshness",
        )]
    else:
        warnings = []
    return warnings


def _unavailable_warning() -> MdmMetricWarning:
    return MdmMetricWarning(
        severity="error",
        message=MDM_UNAVAILABLE_MESSAGE,
        action="Set MDM_DATABASE_URL, verify network access, and restart the dashboard.",
    )


def _unavailable_metrics() -> MdmDashboardMetrics:
    return MdmDashboardMetrics(
        available=False,
        message=MDM_UNAVAILABLE_MESSAGE,
        entity_counts={},
        relationship_counts={},
        pending_sync_samples=[],
        warnings=[_unavailable_warning()],
        registry={},
        error_env_var=MDM_DATABASE_ENV_VAR,
    )


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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _close_owned_session(session: Session | None) -> None:
    if session is None:
        return
    try:
        session.rollback()
    finally:
        session.close()
