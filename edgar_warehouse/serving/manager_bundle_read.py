"""Manager Subject Bundle — ADV / fund / IS_ENTITY_OF sections (ticket 12).

Agent-grade ADV and MANAGES_FUND edges require **bulk IAPD** provenance.
Heuristic ADV parses are never agent-grade. Pure issuer bundles (ticket 11)
keep ADV ``not_applicable`` and are unchanged by this module.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from edgar_warehouse.serving.decision_contract import (
    DECISION_CONTRACT_VERSION,
    evaluate_agent_grade,
)
from edgar_warehouse.serving.subject_bundle_read import (
    SECTION_ADV,
    SECTION_SUBJECT_AS_MANAGER_PORTFOLIO,
    SECTION_SUBJECT_FEATURES,
    _build_holdings_section,
    _build_subject_features_section,
    _watermark_identity,
)
from edgar_warehouse.serving.subject_feature_screen import (
    COVERAGE_EMPTY,
    COVERAGE_NOT_APPLICABLE,
    COVERAGE_PRESENT,
    COVERAGE_UNAVAILABLE,
)

SECTION_MANAGES_FUND = "manages_fund"
SECTION_IS_ENTITY_OF = "is_entity_of"

# Provenance tags for fund/ADV edges
ADV_SOURCE_BULK_IAPD = "bulk_iapd"
ADV_SOURCE_HEURISTIC = "heuristic_adv_parse"
AGENT_GRADE_ADV_SOURCES = frozenset(
    {
        ADV_SOURCE_BULK_IAPD,
        "iapd_bulk",
        "iapd_form_adv_bulk",
        "bulk_iapd_part1",
    }
)


def build_manager_subject_bundle(
    *,
    subject_cik: int,
    watermark_components: Mapping[str, Any],
    manages_fund_edges: Sequence[Mapping[str, Any]] = (),
    is_entity_of_edges: Sequence[Mapping[str, Any]] = (),
    subject_as_manager_portfolio: Sequence[Mapping[str, Any]] = (),
    holdings_period: Mapping[str, Any] | None = None,
    period_rows: Sequence[Mapping[str, Any]] = (),
    adv_lag_metadata: Mapping[str, Any] | None = None,
    subject_in_decision_universe: bool = True,
) -> dict[str, Any]:
    """Build a manager/adviser Subject Bundle with ADV-capable sections."""
    cik = int(subject_cik)
    grade = evaluate_agent_grade(watermark_components)
    wm_identity = _watermark_identity(grade)

    if not subject_in_decision_universe:
        return {
            "bundle_subject_cik": cik,
            "bundle_kind": "manager",
            "decision_contract_version": grade.decision_contract_version
            or DECISION_CONTRACT_VERSION,
            "decision_watermark_identity": wm_identity,
            "agent_grade": False,
            "agent_grade_reasons": list(grade.reasons)
            + ["subject not in Decision Subject Universe"],
            "sections": {},
        }

    funds = build_manages_fund_section(manages_fund_edges)
    entity_of = build_is_entity_of_section(is_entity_of_edges)
    adv = build_adv_section_for_manager(
        manages_fund_edges=manages_fund_edges,
        adv_lag_metadata=adv_lag_metadata,
    )
    portfolio = _build_holdings_section(
        subject_as_manager_portfolio,
        holdings_period if subject_as_manager_portfolio else None,
        section_name=SECTION_SUBJECT_AS_MANAGER_PORTFOLIO,
        allow_empty_period_meta=True,
    )
    features = _build_subject_features_section(period_rows)

    return {
        "bundle_subject_cik": cik,
        "bundle_kind": "manager",
        "decision_contract_version": grade.decision_contract_version
        or DECISION_CONTRACT_VERSION,
        "decision_watermark_identity": wm_identity,
        "agent_grade": grade.agent_grade,
        "agent_grade_reasons": list(grade.reasons),
        "sections": {
            SECTION_MANAGES_FUND: funds,
            SECTION_IS_ENTITY_OF: entity_of,
            SECTION_ADV: adv,
            SECTION_SUBJECT_AS_MANAGER_PORTFOLIO: portfolio,
            SECTION_SUBJECT_FEATURES: features,
        },
    }


def build_manages_fund_section(
    edges: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """MANAGES_FUND: only bulk-IAPD edges are agent-grade."""
    agent_rows: list[dict[str, Any]] = []
    non_agent: list[dict[str, Any]] = []
    for edge in edges:
        source = _adv_source(edge)
        row = {
            "fund_entity_id": edge.get("fund_entity_id") or edge.get("entity_id"),
            "fund_name": edge.get("fund_name") or edge.get("name"),
            "adviser_crd": edge.get("adviser_crd"),
            "relationship_type": "MANAGES_FUND",
            "source_system": source,
        }
        if source in AGENT_GRADE_ADV_SOURCES:
            row["agent_grade_edge"] = True
            agent_rows.append(row)
        else:
            row["agent_grade_edge"] = False
            row["reason"] = "heuristic_adv_not_agent_grade"
            non_agent.append(row)

    if agent_rows:
        coverage = COVERAGE_PRESENT
    elif edges:
        coverage = COVERAGE_EMPTY  # only heuristic / non-agent inputs
    else:
        coverage = COVERAGE_UNAVAILABLE

    return {
        "coverage": coverage,
        "rows": agent_rows,
        "non_agent_grade": non_agent,
    }


def build_is_entity_of_section(
    edges: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """IS_ENTITY_OF when adviser CIK and company CIK both resolve.

    Sparse/zero resolved edges are empty/unavailable — never hard-fail issuers
    (issuers use a different builder and do not require this section).
    """
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for edge in edges:
        adviser = edge.get("adviser_cik") or edge.get("manager_cik")
        company = edge.get("company_cik") or edge.get("issuer_cik")
        if adviser is not None and str(adviser).strip() and company is not None and str(company).strip():
            resolved.append(
                {
                    "adviser_cik": int(adviser),
                    "company_cik": int(company),
                    "relationship_type": "IS_ENTITY_OF",
                    "agent_grade_edge": True,
                }
            )
        else:
            unresolved.append(
                {
                    "adviser_cik": adviser,
                    "company_cik": company,
                    "agent_grade_edge": False,
                    "reason": "unresolved_entity_side",
                }
            )

    if resolved:
        coverage = COVERAGE_PRESENT
    elif edges:
        coverage = COVERAGE_EMPTY
    else:
        coverage = COVERAGE_UNAVAILABLE

    return {
        "coverage": coverage,
        "rows": resolved,
        "unresolved": unresolved,
    }


def build_adv_section_for_manager(
    *,
    manages_fund_edges: Sequence[Mapping[str, Any]] = (),
    adv_lag_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Manager ADV neighborhood: agent-grade only from bulk IAPD; lag metadata when present."""
    funds = build_manages_fund_section(manages_fund_edges)
    agent_grade_present = funds["coverage"] == COVERAGE_PRESENT

    lag = None
    if agent_grade_present and adv_lag_metadata:
        lag = {
            "adv_as_of_date": adv_lag_metadata.get("adv_as_of_date")
            or adv_lag_metadata.get("source_dataset_period"),
            "lag_days": adv_lag_metadata.get("lag_days"),
            "source_system": ADV_SOURCE_BULK_IAPD,
            "watermark_component": "adv_bulk_iapd",
        }
    elif agent_grade_present:
        lag = {
            "adv_as_of_date": None,
            "lag_days": None,
            "source_system": ADV_SOURCE_BULK_IAPD,
            "watermark_component": "adv_bulk_iapd",
        }

    return {
        "coverage": funds["coverage"]
        if funds["coverage"] != COVERAGE_UNAVAILABLE
        else COVERAGE_UNAVAILABLE,
        "agent_grade_rows": funds["rows"],
        "non_agent_grade": funds["non_agent_grade"],
        "adv_lag_metadata": lag,
        "reason": None
        if agent_grade_present
        else (
            "no_bulk_iapd_fund_edges"
            if manages_fund_edges
            else "no_adv_inputs"
        ),
    }


def issuer_adv_remains_not_applicable(issuer_bundle: Mapping[str, Any]) -> bool:
    """Regression helper: ticket 11 issuer ADV section must stay not_applicable."""
    sections = issuer_bundle.get("sections") or {}
    adv = sections.get(SECTION_ADV) or {}
    return (
        issuer_bundle.get("bundle_kind") == "issuer"
        and adv.get("coverage") == COVERAGE_NOT_APPLICABLE
    )


def _adv_source(edge: Mapping[str, Any]) -> str:
    raw = (
        edge.get("source_system")
        or edge.get("evidence_source")
        or edge.get("source")
        or ""
    )
    return str(raw).strip().lower() or ADV_SOURCE_HEURISTIC
