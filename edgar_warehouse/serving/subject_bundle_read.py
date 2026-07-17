"""Subject Bundle Read — issuer Trading-Relevant Neighborhood (ticket 11 / ADR 0001).

Single-subject Decision Graph Bundle rooted at Bundle Subject (CIK): Current
Neighborhood sections, As-Of subject features, coverage flags, Decision
Watermark, and Decision Contract Version. Pure issuers set ADV
``not_applicable`` (manager ADV is ticket 12).

Snowflake SQL sketch: ``infra/snowflake/sql/decision_contract/``.
This module is the unit-tested contract semantics layer.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from edgar_warehouse.serving.decision_contract import (
    DECISION_CONTRACT_VERSION,
    evaluate_agent_grade,
)
from edgar_warehouse.serving.subject_feature_screen import (
    COVERAGE_EMPTY,
    COVERAGE_NOT_APPLICABLE,
    COVERAGE_PRESENT,
    COVERAGE_UNAVAILABLE,
    PURE_SEC_FEATURE_KEYS,
    select_as_of_feature_periods,
)

# Section names on the issuer bundle (stable contract surface)
SECTION_INSIDERS = "insiders"
SECTION_EMPLOYMENT = "employment"
SECTION_HOLDERS_OF_SUBJECT = "holders_of_subject"
SECTION_SUBJECT_AS_MANAGER_PORTFOLIO = "subject_as_manager_portfolio"
SECTION_AUDITOR = "auditor"
SECTION_PARENT = "has_parent"
SECTION_SUBJECT_FEATURES = "subject_features"
SECTION_ADV = "adv"

EMPLOYMENT_SOURCE_PROXY = "proxy_def14a"
EMPLOYMENT_SOURCE_ITEM_502 = "item_5_02"
EMPLOYMENT_SOURCE_SYSTEMS = frozenset({EMPLOYMENT_SOURCE_PROXY, EMPLOYMENT_SOURCE_ITEM_502})


def build_issuer_subject_bundle(
    *,
    subject_cik: int,
    watermark_components: Mapping[str, Any],
    graph_insider_edges: Sequence[Mapping[str, Any]] = (),
    gold_ownership_rows: Sequence[Mapping[str, Any]] = (),
    employment_edges: Sequence[Mapping[str, Any]] = (),
    executive_pay_rows: Sequence[Mapping[str, Any]] = (),
    holders_of_subject: Sequence[Mapping[str, Any]] = (),
    subject_as_manager_portfolio: Sequence[Mapping[str, Any]] = (),
    holdings_period: Mapping[str, Any] | None = None,
    auditor_edges: Sequence[Mapping[str, Any]] = (),
    parent_edges: Sequence[Mapping[str, Any]] = (),
    parent_inventory_complete: bool = False,
    period_rows: Sequence[Mapping[str, Any]] = (),
    include_neighborhood_history: bool = False,
    subject_in_decision_universe: bool = True,
) -> dict[str, Any]:
    """Build an issuer Subject Bundle Read payload.

    Parameters are pre-filtered to the subject (or current neighborhood). Graph
    vs gold joining for insiders happens here so agent-grade edges require both.
    """
    cik = int(subject_cik)
    grade = evaluate_agent_grade(watermark_components)
    wm_identity = _watermark_identity(grade)

    if not subject_in_decision_universe:
        return {
            "bundle_subject_cik": cik,
            "bundle_kind": "issuer",
            "decision_contract_version": grade.decision_contract_version
            or DECISION_CONTRACT_VERSION,
            "decision_watermark_identity": wm_identity,
            "agent_grade": False,
            "agent_grade_reasons": list(grade.reasons)
            + ["subject not in Decision Subject Universe"],
            "sections": {},
            "include_neighborhood_history": bool(include_neighborhood_history),
        }

    insiders = _build_insiders_section(graph_insider_edges, gold_ownership_rows)
    employment = _build_employment_section(employment_edges, executive_pay_rows)
    holders = _build_holdings_section(
        holders_of_subject,
        holdings_period,
        section_name=SECTION_HOLDERS_OF_SUBJECT,
    )
    manager_book = _build_holdings_section(
        subject_as_manager_portfolio,
        holdings_period if subject_as_manager_portfolio else None,
        section_name=SECTION_SUBJECT_AS_MANAGER_PORTFOLIO,
        allow_empty_period_meta=True,
    )
    auditor = _build_auditor_section(auditor_edges)
    parent = _build_parent_section(parent_edges, parent_inventory_complete)
    features = _build_subject_features_section(period_rows)
    adv = {
        "coverage": COVERAGE_NOT_APPLICABLE,
        "reason": "pure_issuer_bundle_does_not_require_adv",
        "rows": [],
    }

    sections = {
        SECTION_INSIDERS: insiders,
        SECTION_EMPLOYMENT: employment,
        SECTION_HOLDERS_OF_SUBJECT: holders,
        SECTION_SUBJECT_AS_MANAGER_PORTFOLIO: manager_book,
        SECTION_AUDITOR: auditor,
        SECTION_PARENT: parent,
        SECTION_SUBJECT_FEATURES: features,
        SECTION_ADV: adv,
    }

    return {
        "bundle_subject_cik": cik,
        "bundle_kind": "issuer",
        "decision_contract_version": grade.decision_contract_version
        or DECISION_CONTRACT_VERSION,
        "decision_watermark_identity": wm_identity,
        "agent_grade": grade.agent_grade,
        "agent_grade_reasons": list(grade.reasons),
        "include_neighborhood_history": bool(include_neighborhood_history),
        "sections": sections,
    }


def _watermark_identity(grade: Any) -> dict[str, Any] | None:
    if grade.watermark is None:
        return None
    wm = grade.watermark
    return {
        "business_date": wm.business_date,
        "gold_run_id": wm.gold_run_id,
        "graph_generation_id": wm.graph_generation_id,
        "decision_contract_version": wm.decision_contract_version,
    }


def _build_insiders_section(
    graph_edges: Sequence[Mapping[str, Any]],
    gold_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Agent-grade insiders require graph IS_INSIDER + gold source accession."""
    gold_by_person: dict[str, list[Mapping[str, Any]]] = {}
    for row in gold_rows:
        key = _person_key(row)
        if not key:
            continue
        gold_by_person.setdefault(key, []).append(row)

    agent_grade_rows: list[dict[str, Any]] = []
    unresolved_graph: list[dict[str, Any]] = []
    for edge in graph_edges:
        key = _person_key(edge)
        accessions = [
            str(r.get("accession_number"))
            for r in gold_by_person.get(key, ())
            if r.get("accession_number")
        ]
        if not key or not accessions:
            unresolved_graph.append(
                {
                    "person_entity_id": edge.get("person_entity_id") or edge.get("entity_id"),
                    "person_name": edge.get("person_name") or edge.get("name"),
                    "reason": "missing_gold_source_accession",
                    "agent_grade_edge": False,
                }
            )
            continue
        agent_grade_rows.append(
            {
                "person_entity_id": edge.get("person_entity_id") or edge.get("entity_id"),
                "person_name": edge.get("person_name") or edge.get("name"),
                "relationship_type": edge.get("relationship_type") or "IS_INSIDER",
                "source_accessions": sorted(set(accessions)),
                "agent_grade_edge": True,
            }
        )

    # Gold-only names without graph resolution are never agent-grade edges
    gold_only = []
    graph_keys = {_person_key(e) for e in graph_edges}
    for key, rows in gold_by_person.items():
        if key in graph_keys:
            continue
        gold_only.append(
            {
                "person_name": rows[0].get("person_name") or rows[0].get("owner_name"),
                "source_accessions": sorted(
                    {str(r["accession_number"]) for r in rows if r.get("accession_number")}
                ),
                "agent_grade_edge": False,
                "reason": "gold_only_unresolved_string",
            }
        )

    if agent_grade_rows:
        coverage = COVERAGE_PRESENT
    elif graph_edges or gold_rows:
        coverage = COVERAGE_EMPTY  # inputs existed but no agent-grade join
    else:
        coverage = COVERAGE_UNAVAILABLE

    return {
        "coverage": coverage,
        "rows": agent_grade_rows,
        "non_agent_grade": {
            "unresolved_graph_edges": unresolved_graph,
            "gold_only_unresolved": gold_only,
        },
    }


def _build_employment_section(
    edges: Sequence[Mapping[str, Any]],
    pay_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for edge in edges:
        source = str(edge.get("source_system") or "").strip()
        if source not in EMPLOYMENT_SOURCE_SYSTEMS:
            # Unknown source — still surface but mark non-standard
            source = source or "unknown"
        rows.append(
            {
                "person_entity_id": edge.get("person_entity_id") or edge.get("entity_id"),
                "person_name": edge.get("person_name") or edge.get("name"),
                "role_title": edge.get("role_title") or edge.get("title"),
                "source_system": source,
                "relationship_type": "EMPLOYED_BY",
                "effective_date": edge.get("effective_date"),
            }
        )

    pay: list[dict[str, Any]] = []
    for row in pay_rows:
        pay.append(
            {
                "person_name": row.get("person_name") or row.get("name"),
                "exec_role": row.get("exec_role") or row.get("role"),
                "compensation_amount": row.get("compensation_amount"),
                "accession_number": row.get("accession_number"),
                "source": "gold_proxy_executive_record",
            }
        )

    if rows:
        coverage = COVERAGE_PRESENT
    elif pay:
        coverage = COVERAGE_EMPTY  # pay without employment edges
    else:
        coverage = COVERAGE_UNAVAILABLE

    return {
        "coverage": coverage,
        "rows": rows,
        "executive_pay": pay,
    }


def _build_holdings_section(
    rows: Sequence[Mapping[str, Any]],
    holdings_period: Mapping[str, Any] | None,
    *,
    section_name: str,
    allow_empty_period_meta: bool = False,
) -> dict[str, Any]:
    """13F section with Latest Complete Holdings Period lag metadata."""
    period_meta = None
    if holdings_period:
        period_meta = {
            "latest_complete_holdings_period": holdings_period.get(
                "latest_complete_holdings_period"
            )
            or holdings_period.get("period_of_report"),
            "period_end": holdings_period.get("period_end"),
            "lag_days": holdings_period.get("lag_days"),
            "as_of_business_date": holdings_period.get("as_of_business_date"),
        }

    if rows:
        coverage = COVERAGE_PRESENT
    elif holdings_period and not allow_empty_period_meta:
        coverage = COVERAGE_EMPTY
    else:
        coverage = COVERAGE_UNAVAILABLE

    return {
        "coverage": coverage,
        "section": section_name,
        "holdings_period": period_meta,
        "rows": [dict(r) for r in rows],
    }


def _build_auditor_section(edges: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    preferred: list[dict[str, Any]] = []
    for edge in edges:
        preferred.append(
            {
                "auditor_entity_id": edge.get("auditor_entity_id") or edge.get("entity_id"),
                "auditor_name": edge.get("auditor_name") or edge.get("name"),
                "pcaob_id": edge.get("pcaob_id"),
                "relationship_type": "AUDITED_BY",
                "source": edge.get("source") or "auditor_evidence",
                "identity_rule": "prefer_auditor_evidence_pcaob_id",
            }
        )
    # Prefer rows that have PCAOB id first (stable identity)
    preferred.sort(key=lambda r: (0 if r.get("pcaob_id") else 1, str(r.get("auditor_name") or "")))

    if preferred:
        coverage = COVERAGE_PRESENT
    else:
        coverage = COVERAGE_UNAVAILABLE

    return {"coverage": coverage, "rows": preferred}


def _build_parent_section(
    edges: Sequence[Mapping[str, Any]],
    inventory_complete: bool,
) -> dict[str, Any]:
    """HAS_PARENT only when subsidiary evidence inventory is complete for the claim."""
    if not inventory_complete:
        return {
            "coverage": COVERAGE_UNAVAILABLE,
            "scope": "registrant_disclosed",
            "inventory_complete": False,
            "rows": [],
            "reason": "parent_inventory_incomplete",
        }
    rows = [
        {
            "parent_entity_id": e.get("parent_entity_id") or e.get("entity_id"),
            "parent_name": e.get("parent_name") or e.get("name"),
            "relationship_type": "HAS_PARENT_COMPANY",
            "scope": "registrant_disclosed",
        }
        for e in edges
    ]
    if rows:
        coverage = COVERAGE_PRESENT
    else:
        coverage = COVERAGE_EMPTY  # inventory complete but no parent disclosed
    return {
        "coverage": coverage,
        "scope": "registrant_disclosed",
        "inventory_complete": True,
        "rows": rows,
    }


def _build_subject_features_section(
    period_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    selected = select_as_of_feature_periods(period_rows)
    fy = selected["fy"]
    interim = selected["interim"]

    def _vec(period: Mapping[str, Any] | None) -> dict[str, Any]:
        if period is None:
            return {k: None for k in PURE_SEC_FEATURE_KEYS}
        return {k: period.get(k) for k in PURE_SEC_FEATURE_KEYS}

    def _cov(period: Mapping[str, Any] | None, *, interim_section: bool) -> str:
        if period is None:
            return COVERAGE_NOT_APPLICABLE if interim_section else COVERAGE_UNAVAILABLE
        vec = _vec(period)
        if any(v is not None for v in vec.values()):
            return COVERAGE_PRESENT
        return COVERAGE_EMPTY

    return {
        "coverage": _cov(fy, interim_section=False),
        "fy_features": _vec(fy),
        "fy_features_coverage": _cov(fy, interim_section=False),
        "fy_period_end": str(fy["period_end"]) if fy else None,
        "interim_features": _vec(interim),
        "interim_features_coverage": _cov(interim, interim_section=True),
        "interim_period_end": str(interim["period_end"]) if interim else None,
    }


def _person_key(row: Mapping[str, Any]) -> str:
    for field in ("person_entity_id", "entity_id", "mdm_person_id"):
        val = row.get(field)
        if val is not None and str(val).strip():
            return f"id:{val}"
    name = row.get("person_name") or row.get("owner_name") or row.get("name")
    if name is not None and str(name).strip():
        return f"name:{str(name).strip().lower()}"
    return ""
