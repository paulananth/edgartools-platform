"""Subject Feature Screen — multi-issuer ranking surface (ticket 10 / ADR 0001).

Flat Decision Contract object over the **Decision Subject Universe**
(warehouse active ∩ MDM active): Primary Annual (FY) + Latest Interim feature
vectors (interim only when newer than FY), pure-SEC metrics only, coverage
flags, and Decision Watermark identity.

Snowflake view SQL lives in ``infra/snowflake/sql/decision_contract/``; this
module is the pure semantics layer unit-tested in-repo.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from edgar_warehouse.serving.decision_contract import (
    DECISION_CONTRACT_VERSION,
    evaluate_agent_grade,
)

# Bundle Coverage Flags (ADR 0001 / product grill)
COVERAGE_PRESENT = "present"
COVERAGE_EMPTY = "empty"
COVERAGE_UNAVAILABLE = "unavailable"
COVERAGE_NOT_APPLICABLE = "not_applicable"

# Pure-SEC Decision Features — no market prices / PE / market cap (ADR 0001).
PURE_SEC_FEATURE_KEYS: tuple[str, ...] = (
    "revenue",
    "gross_profit",
    "ebitda",
    "ebit",
    "net_income",
    "eps_diluted",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "cash_and_equivalents",
    "total_debt",
    "operating_cash_flow",
    "free_cash_flow",
    "gross_margin",
    "ebitda_margin",
    "net_margin",
    "roe",
    "roa",
    "roic",
)

FORBIDDEN_MARKET_FIELDS: frozenset[str] = frozenset(
    {
        "price",
        "market_price",
        "close_price",
        "market_cap",
        "market_capitalization",
        "pe",
        "pe_ratio",
        "p_e",
        "price_to_earnings",
        "enterprise_value",
        "ev",
        "ev_ebitda",
    }
)

_FY_PERIODS = frozenset({"FY", "fy", "annual", "YEAR"})
_INTERIM_PERIODS = frozenset({"Q1", "Q2", "Q3", "Q4", "H1", "H2", "q1", "q2", "q3", "q4"})


def decision_subject_universe(
    *,
    warehouse_active_ciks: Iterable[int],
    mdm_active_ciks: Iterable[int],
) -> tuple[int, ...]:
    """Decision Subject Universe = warehouse active ∩ MDM active (ticket 14)."""
    left = {int(c) for c in warehouse_active_ciks}
    right = {int(c) for c in mdm_active_ciks}
    return tuple(sorted(left & right))


def select_as_of_feature_periods(
    period_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any] | None]:
    """Pick Primary Annual FY and Latest Interim if newer than that FY.

    Null metrics stay null (null ≠ zero). Historic series are not returned —
    only the as-of slice for ranking.
    """
    fy_candidates: list[Mapping[str, Any]] = []
    interim_candidates: list[Mapping[str, Any]] = []
    for row in period_rows:
        period = str(row.get("fiscal_period") or "").strip()
        if period in _FY_PERIODS or period.upper() == "FY":
            fy_candidates.append(row)
        elif period in _INTERIM_PERIODS or period.upper().startswith("Q"):
            interim_candidates.append(row)

    fy = _latest_by_period_end(fy_candidates)
    interim: Mapping[str, Any] | None = None
    if fy is not None:
        fy_end = str(fy.get("period_end") or "")
        newer = [
            r
            for r in interim_candidates
            if str(r.get("period_end") or "") > fy_end
        ]
        interim = _latest_by_period_end(newer)
    else:
        interim = _latest_by_period_end(interim_candidates)

    return {"fy": fy, "interim": interim}


def build_subject_feature_screen(
    *,
    warehouse_active_ciks: Iterable[int],
    mdm_active_ciks: Iterable[int],
    period_rows: Sequence[Mapping[str, Any]],
    watermark_components: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a Subject Feature Screen payload for agent rank/filter.

    Returns decision_contract_version, agent_grade evaluation, watermark
    identity, and one row per universe CIK (even when features unavailable).
    """
    grade = evaluate_agent_grade(watermark_components)
    universe = decision_subject_universe(
        warehouse_active_ciks=warehouse_active_ciks,
        mdm_active_ciks=mdm_active_ciks,
    )
    by_cik: dict[int, list[Mapping[str, Any]]] = {}
    for row in period_rows:
        try:
            cik = int(row["cik"])
        except (KeyError, TypeError, ValueError):
            continue
        by_cik.setdefault(cik, []).append(row)

    screen_rows: list[dict[str, Any]] = []
    for cik in universe:
        selected = select_as_of_feature_periods(by_cik.get(cik, ()))
        fy_vec, fy_cov = _vector_and_coverage(selected["fy"], section="fy")
        interim_vec, interim_cov = _vector_and_coverage(
            selected["interim"], section="interim"
        )
        screen_rows.append(
            {
                "cik": cik,
                "fy_features": fy_vec,
                "fy_features_coverage": fy_cov,
                "fy_period_end": (
                    str(selected["fy"].get("period_end")) if selected["fy"] else None
                ),
                "fy_fiscal_year": (
                    selected["fy"].get("fiscal_year") if selected["fy"] else None
                ),
                "fy_accession_number": (
                    selected["fy"].get("accession_number") if selected["fy"] else None
                ),
                "interim_features": interim_vec,
                "interim_features_coverage": interim_cov,
                "interim_period_end": (
                    str(selected["interim"].get("period_end"))
                    if selected["interim"]
                    else None
                ),
                "interim_fiscal_period": (
                    selected["interim"].get("fiscal_period")
                    if selected["interim"]
                    else None
                ),
                "interim_accession_number": (
                    selected["interim"].get("accession_number")
                    if selected["interim"]
                    else None
                ),
                "decision_contract_version": grade.decision_contract_version,
                "decision_watermark_identity": _watermark_identity(grade),
            }
        )

    return {
        "decision_contract_version": grade.decision_contract_version
        or DECISION_CONTRACT_VERSION,
        "agent_grade": grade.agent_grade,
        "agent_grade_reasons": list(grade.reasons),
        "decision_watermark_identity": _watermark_identity(grade),
        "universe_size": len(universe),
        "rows": screen_rows,
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


def _latest_by_period_end(
    rows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    if not rows:
        return None
    return max(rows, key=lambda r: str(r.get("period_end") or ""))


def _vector_and_coverage(
    period: Mapping[str, Any] | None,
    *,
    section: str,
) -> tuple[dict[str, Any], str]:
    if period is None:
        if section == "interim":
            # Interim is optional on the screen: missing newer interim is
            # not_applicable (not a hard gap).
            return _empty_vector(), COVERAGE_NOT_APPLICABLE
        return _empty_vector(), COVERAGE_UNAVAILABLE
    vector = _feature_vector(period)
    if any(v is not None for v in vector.values()):
        return vector, COVERAGE_PRESENT
    return vector, COVERAGE_EMPTY


def _feature_vector(period: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in PURE_SEC_FEATURE_KEYS:
        if key in FORBIDDEN_MARKET_FIELDS:
            continue
        if key not in period:
            out[key] = None
            continue
        value = period.get(key)
        # Preserve explicit null — never coerce to 0.
        out[key] = value
    return out


def _empty_vector() -> dict[str, Any]:
    return {key: None for key in PURE_SEC_FEATURE_KEYS}
