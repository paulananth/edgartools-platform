"""EntityFacts parser — XBRL financial facts + DEI auditor data.

Architecture note
-----------------
EntityFacts is CIK-level, NOT per-filing.  The SEC endpoint
``/api/xbrl/companyfacts/CIK{cik:010}.json`` returns *all* historical
XBRL facts for a company in a single JSON blob.

This parser does NOT go through the standard ``get_parser()`` per-filing
dispatch.  The orchestrator calls ``parse_entity_facts(cik, facts_json)``
directly for each CIK during the ``bootstrap-entity-facts`` command.

Output tables
-------------
``sec_financial_fact``    — one row per (cik, accession, concept, fiscal_period, segment)
``sec_accounting_flag``   — one row per (cik, accession) from 10-K DEI facts
                           (forensic scores remain NULL; computed by accounting_flags.py)

Usage
-----
    from edgar_warehouse.parsers.financials import parse_entity_facts

    results = parse_entity_facts(cik=320193, facts_json=raw_json_dict)
    silver.write_table("sec_financial_fact", results["sec_financial_fact"])
    silver.write_table("sec_accounting_flag", results["sec_accounting_flag"])
"""

from __future__ import annotations

from typing import Any

PARSER_NAME = "entity_facts_v1"
PARSER_VERSION = "1"

# Accepted fiscal period labels.  Instantaneous snapshots ("CY2024Q1I" etc.)
# and non-standard periods are excluded to keep the table focused.
_VALID_FISCAL_PERIODS = frozenset({"FY", "Q1", "Q2", "Q3", "Q4"})

# DEI concepts that feed sec_accounting_flag
_DEI_AUDITOR_CONCEPTS = {
    "AuditorFirmId":               "auditor_pcaob_id",
    "AuditorName":                 "auditor_name",
    "AuditorLocation":             "auditor_location",
    "IcfrAuditorAttestationFlag":  "icfr_attestation",
}

# Forms that carry annual financial statements
_ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "20-F", "20-F/A"})


def parse_entity_facts(
    cik: int,
    facts_json: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Parse SEC EntityFacts JSON into silver table rows.

    Parameters
    ----------
    cik:
        Company CIK (integer).
    facts_json:
        Raw dict from the SEC ``companyfacts`` API endpoint.

    Returns
    -------
    dict with keys:
      ``"sec_financial_fact"``   — list of XBRL fact row dicts
      ``"sec_accounting_flag"``  — list of auditor-info row dicts (10-K only)
    """
    if not facts_json or "facts" not in facts_json:
        return {"sec_financial_fact": [], "sec_accounting_flag": []}

    facts_section: dict[str, Any] = facts_json.get("facts", {})

    financial_rows: list[dict[str, Any]] = []
    accounting_rows: list[dict[str, Any]] = []

    # ── us-gaap facts → sec_financial_fact ───────────────────────────────────
    usgaap = facts_section.get("us-gaap", {})
    for concept, concept_data in usgaap.items():
        for unit, unit_facts in concept_data.get("units", {}).items():
            for fact in unit_facts:
                row = _extract_financial_fact_row(cik, concept, unit, fact)
                if row is not None:
                    financial_rows.append(row)

    # ── dei facts → sec_accounting_flag (10-K rows only) ────────────────────
    dei = facts_section.get("dei", {})
    # Collect per-accession DEI values before building rows
    accn_dei: dict[str, dict[str, Any]] = {}

    for dei_concept, col_name in _DEI_AUDITOR_CONCEPTS.items():
        concept_data = dei.get(dei_concept, {})
        for unit, unit_facts in concept_data.get("units", {}).items():
            for fact in unit_facts:
                accn = fact.get("accn", "")
                form = fact.get("form", "")
                if not accn or form not in _ANNUAL_FORMS:
                    continue

                if accn not in accn_dei:
                    accn_dei[accn] = {
                        "cik": int(cik),
                        "accession_number": accn,
                        "fiscal_year": _to_int(fact.get("fy")),
                        "period_end": fact.get("end"),
                        "form_type": form,
                        "auditor_name": None,
                        "auditor_pcaob_id": None,
                        "auditor_location": None,
                        "icfr_attestation": None,
                        "auditor_changed": None,  # computed by accounting_flags.backfill
                        "beneish_m_score": None,  # computed by accounting_flags.backfill
                        "altman_z_score": None,   # computed by accounting_flags.backfill
                        "piotroski_f_score": None,  # computed by accounting_flags.backfill
                        "parser_version": PARSER_VERSION,
                    }

                raw_val = fact.get("val")
                if col_name == "icfr_attestation":
                    accn_dei[accn][col_name] = _parse_bool_flag(raw_val)
                elif col_name == "auditor_pcaob_id":
                    accn_dei[accn][col_name] = str(int(raw_val)) if raw_val is not None else None
                else:
                    accn_dei[accn][col_name] = str(raw_val).strip() if raw_val is not None else None

    accounting_rows = list(accn_dei.values())

    return {
        "sec_financial_fact": financial_rows,
        "sec_accounting_flag": accounting_rows,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_financial_fact_row(
    cik: int,
    concept: str,
    unit: str,
    fact: dict[str, Any],
) -> dict[str, Any] | None:
    """Build a single ``sec_financial_fact`` row, or None if the fact should
    be skipped (missing accession, invalid fiscal period, etc.)."""
    accn = fact.get("accn", "")
    if not accn:
        return None

    fp = fact.get("fp", "")
    if fp not in _VALID_FISCAL_PERIODS:
        return None

    val = fact.get("val")

    return {
        "cik": int(cik),
        "accession_number": accn,
        "fiscal_year": _to_int(fact.get("fy")),
        "fiscal_period": fp,
        "period_end": fact.get("end"),
        "form_type": fact.get("form", ""),
        "concept": concept,
        "value": _to_float(val),
        "unit": unit,
        "decimals": _to_int(fact.get("decimals")),
        "segment": "consolidated",  # EntityFacts JSON does not expose segment breakdowns
        "parser_version": PARSER_VERSION,
    }


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_bool_flag(value: Any) -> bool | None:
    """Parse dei:IcfrAuditorAttestationFlag — typically 'true'/'false' string."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None
