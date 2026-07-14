"""Coverage reporting: compare silver source counts to MDM entity counts per domain.

Pure compute core — no side effects, no CLI concerns.
"""
from __future__ import annotations

import hashlib
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session


def compute_coverage(silver_reader: Any, session: Session) -> list[dict]:
    """Return per-domain silver_count vs mdm_count comparison.

    Predicates mirror pipeline.py loader queries exactly so gaps reflect real
    loader misses, not measurement drift.

    Each returned dict has: domain, silver_count, mdm_count, gap, reason.
    gap = silver_count - mdm_count.  Positive gap = loader missed records.
    """
    from sqlalchemy import func, select

    from edgar_warehouse.mdm.database import (
        MdmAdviser,
        MdmCompany,
        MdmFund,
        MdmPerson,
        MdmSecurity,
    )

    def _silver(sql: str) -> int:
        rows = silver_reader.fetch(sql)
        if not rows:
            return 0
        first = rows[0]
        return int(list(first.values())[0] or 0)

    def _mdm_count(model) -> int:
        return session.scalar(select(func.count()).select_from(model)) or 0

    # ------------------------------------------------------------------
    # Companies — active tracking_status via sec_company_sync_state join.
    # Mirrors: run_companies iterates sec_company and checks sync_state per row.
    # Inactive/dropped companies (no active sync_state) are excluded.
    # ------------------------------------------------------------------
    company_silver = _silver(
        "SELECT COUNT(DISTINCT c.cik) AS n "
        "FROM sec_company c "
        "JOIN sec_company_sync_state s ON s.cik = c.cik "
        "WHERE s.tracking_status = 'active'"
    )
    company_mdm = _mdm_count(MdmCompany)

    # ------------------------------------------------------------------
    # Persons — non-corporate reporting owners.
    # Mirrors: run_persons excludes owner_cik values present in sec_company
    # (the silver-side proxy for _company_cik_set()).
    # ------------------------------------------------------------------
    person_silver = _silver(
        "SELECT COUNT(DISTINCT o.owner_cik) AS n "
        "FROM sec_ownership_reporting_owner o "
        "JOIN sec_company_filing f ON o.accession_number = f.accession_number "
        "WHERE o.owner_name IS NOT NULL "
        "  AND (o.owner_cik IS NULL "
        "       OR o.owner_cik NOT IN (SELECT cik FROM sec_company))"
    )
    person_mdm = _mdm_count(MdmPerson)

    # ------------------------------------------------------------------
    # Securities — ownership-sourced transactions only.
    # Mirrors: run_securities UNION ALL of non-derivative + derivative txns.
    # XBRL-sourced securities (sec_financial_fact) are deferred to Phase 6.
    # ------------------------------------------------------------------
    security_silver = _silver(
        "SELECT COUNT(*) AS n FROM ("
        "  SELECT t.accession_number, t.owner_index, t.txn_index"
        "  FROM sec_ownership_non_derivative_txn t"
        "  JOIN sec_company_filing f ON t.accession_number = f.accession_number"
        "  WHERE t.security_title IS NOT NULL"
        "  UNION ALL"
        "  SELECT t.accession_number, t.owner_index, t.txn_index"
        "  FROM sec_ownership_derivative_txn t"
        "  JOIN sec_company_filing f ON t.accession_number = f.accession_number"
        "  WHERE t.security_title IS NOT NULL"
        ")"
    )
    security_mdm = _mdm_count(MdmSecurity)

    # ------------------------------------------------------------------
    # Advisers — all ADV filers.
    # Mirrors: run_advisers iterates all sec_adv_filing rows.
    # ------------------------------------------------------------------
    adviser_silver = _silver("SELECT COUNT(*) AS n FROM sec_adv_filing")
    adviser_mdm = _mdm_count(MdmAdviser)

    # ------------------------------------------------------------------
    # Funds — all private funds (zero acceptable exclusions per D-21).
    # Mirrors: run_funds iterates all sec_adv_private_fund rows.
    # ------------------------------------------------------------------
    fund_silver = _silver("SELECT COUNT(*) AS n FROM sec_adv_private_fund")
    fund_mdm = _mdm_count(MdmFund)

    return [
        {
            "domain": "companies",
            "silver_count": company_silver,
            "mdm_count": company_mdm,
            "gap": company_silver - company_mdm,
            "reason": "Inactive and dropped companies excluded (tracking_status != 'active')",
        },
        {
            "domain": "persons",
            "silver_count": person_silver,
            "mdm_count": person_mdm,
            "gap": person_silver - person_mdm,
            "reason": "Corporate owners (owner_cik in company CIK set) excluded",
        },
        {
            "domain": "securities",
            "silver_count": security_silver,
            "mdm_count": security_mdm,
            "gap": security_silver - security_mdm,
            "reason": (
                "Ownership-sourced only; XBRL-sourced securities "
                "(sec_financial_fact) deferred to Phase 6 per D-24/D-28"
            ),
        },
        {
            "domain": "advisers",
            "silver_count": adviser_silver,
            "mdm_count": adviser_mdm,
            "gap": adviser_silver - adviser_mdm,
            "reason": "All ADV filers included (no exclusions)",
        },
        {
            "domain": "funds",
            "silver_count": fund_silver,
            "mdm_count": fund_mdm,
            "gap": fund_silver - fund_mdm,
            "reason": "All private funds included (zero acceptable exclusions per D-21)",
        },
    ]


# ---------------------------------------------------------------------------
# Relationship coverage manifest (07-02, RCOV-01/02)
# ---------------------------------------------------------------------------

RELATIONSHIP_COVERAGE_STATUSES = ("populated", "valid_zero", "excluded")

POPULATED_RELATIONSHIP_TYPES = ("IS_INSIDER", "HOLDS", "COMPANY_HOLDS", "ISSUED_BY")
"""Types with nonzero graph-verified edges as of Phase 5/6. Kept here (not
imported from snowflake_graph.py, which has no dependency on this module) so
the exclusion/valid-zero classifiers below stay a single source of truth;
tests/mdm/test_relationship_coverage.py asserts this matches
snowflake_graph.POPULATED_RELATIONSHIP_TYPES."""

# Bumped only when a new parser/capability that could produce HAS_PARENT_COMPANY
# is added (e.g. an Exhibit 21 parent/subsidiary parser). See
# edgar_warehouse/mdm/resolvers/company.py's _parent_company_entity_id, which
# unconditionally returns None today because no _PARENT_CIK_KEYS source column
# exists on sec_company.
EDGE08_PARSER_CAPABILITY_VERSION = "no-exhibit21-parser-v1"


def _fingerprint(*parts: Iterable[Any]) -> str:
    """Deterministic sha256 over sorted, stringified parts.

    Stable for the same sorted input; changes whenever the evaluated
    population (or a capability-version marker standing in for it) changes.
    """
    flattened: list[str] = []
    for part in parts:
        flattened.extend(str(p) for p in part)
    joined = "|".join(sorted(flattened))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def compute_edge05_is_entity_of_coverage(session: Session) -> dict:
    """EDGE-05 IS_ENTITY_OF (adviser->company): D-04 zero-overlap exclusion.

    Reproduces AdviserResolver._link_to_company's join independently:
    MdmCompany.cik == MdmAdviser.cik. Scoped to the current tracking-list
    universe -- the fingerprint is the sorted union of both CIK sets, so any
    change to either population invalidates a stored record.
    """
    from edgar_warehouse.mdm.database import MdmAdviser, MdmCompany
    from sqlalchemy import select

    adviser_ciks = sorted(str(c) for c in session.scalars(select(MdmAdviser.cik)) if c is not None)
    company_ciks = sorted(str(c) for c in session.scalars(select(MdmCompany.cik)) if c is not None)
    overlap = set(adviser_ciks) & set(company_ciks)
    return {
        "status": "excluded",
        "evidence_category": "scoped_zero_overlap",
        "expected_edge_count": 0,
        "evidence_query_version": "edge05-v1",
        "population_fingerprint": _fingerprint(adviser_ciks, company_ciks),
        "review_trigger": (
            f"Re-run if the adviser or company universe grows (currently "
            f"{len(adviser_ciks)} adviser CIK(s), {len(company_ciks)} company CIK(s), "
            f"{len(overlap)} overlapping)."
        ),
    }


def compute_edge06_is_person_of_coverage(session: Session) -> dict:
    """EDGE-06 IS_PERSON_OF (adviser->person): D-04 zero-overlap exclusion.

    Reproduces pipeline.py's _adviser_person_pairs join independently:
    MdmPerson.owner_cik == MdmAdviser.cik.
    """
    from edgar_warehouse.mdm.database import MdmAdviser, MdmPerson
    from sqlalchemy import select

    adviser_ciks = sorted(str(c) for c in session.scalars(select(MdmAdviser.cik)) if c is not None)
    owner_ciks = sorted(
        str(c) for c in session.scalars(select(MdmPerson.owner_cik)) if c is not None
    )
    overlap = set(adviser_ciks) & set(owner_ciks)
    return {
        "status": "excluded",
        "evidence_category": "scoped_zero_overlap",
        "expected_edge_count": 0,
        "evidence_query_version": "edge06-v1",
        "population_fingerprint": _fingerprint(adviser_ciks, owner_ciks),
        "review_trigger": (
            f"Re-run if the adviser or person universe grows (currently "
            f"{len(adviser_ciks)} adviser CIK(s), {len(owner_ciks)} person owner_cik(s), "
            f"{len(overlap)} overlapping)."
        ),
    }


def compute_edge07_manages_fund_coverage(silver_reader: Any, session: Session) -> dict:
    """EDGE-07 MANAGES_FUND (adviser->fund): source_unavailable exclusion.

    Evidence: every tracked adviser CIK's EDGAR submission-index accession
    history for ADV-family forms. Form ADV Part 1A / Schedule D (the
    document that would carry private-fund management data) is filed
    through IARD, not EDGAR -- confirmed live for a representative sample
    (SEC submissions.json for 3 tracked adviser CIKs showed only ADV-E/
    13F-HR/N-PX, never a primary ADV/ADV-A entry). Fingerprinted on the
    adviser CIK population and their actual ADV-family accessions, so
    growth of the universe or a new primary ADV filing invalidates staleness.
    """
    from edgar_warehouse.mdm.database import MdmAdviser
    from sqlalchemy import select

    adviser_ciks = sorted(str(c) for c in session.scalars(select(MdmAdviser.cik)) if c is not None)
    rows = silver_reader.fetch(
        "SELECT cik, form, accession_number FROM sec_company_filing WHERE form LIKE 'ADV%'"
    )
    evidence_keys = sorted(f"{r['cik']}:{r['form']}:{r['accession_number']}" for r in rows)
    return {
        "status": "excluded",
        "evidence_category": "source_unavailable",
        "expected_edge_count": 0,
        "evidence_query_version": "edge07-v1",
        "population_fingerprint": _fingerprint(adviser_ciks, evidence_keys),
        "review_trigger": (
            "Re-evaluate if any tracked adviser CIK's sec_company_filing history "
            "gains a primary 'ADV' or 'ADV-A' form entry (current EDGAR history for "
            "every ADV-family filer in the tracked universe contains only notice "
            "sub-forms such as ADV-E/ADV-NR; Form ADV Part 1A/Schedule D private-fund "
            "registration is an IARD artifact, not an EDGAR one)."
        ),
    }


def compute_edge08_has_parent_company_coverage(session: Session) -> dict:
    """EDGE-08 HAS_PARENT_COMPANY (company->company): capability_not_implemented.

    Confirmed via code reading: resolvers/company.py's
    _parent_company_entity_id always returns None because no
    _PARENT_CIK_KEYS source column exists on sec_company (would require an
    Exhibit 21 or equivalent parser this platform does not have). Fingerprint
    is on the company population size plus the parser-capability version --
    bump EDGE08_PARSER_CAPABILITY_VERSION when that parser is added.
    """
    from edgar_warehouse.mdm.database import MdmCompany
    from sqlalchemy import func, select

    company_count = session.scalar(select(func.count()).select_from(MdmCompany)) or 0
    return {
        "status": "excluded",
        "evidence_category": "capability_not_implemented",
        "expected_edge_count": 0,
        "evidence_query_version": "edge08-v1",
        "population_fingerprint": _fingerprint([str(company_count)], [EDGE08_PARSER_CAPABILITY_VERSION]),
        "review_trigger": (
            "Re-evaluate when an Exhibit 21 (or equivalent parent/subsidiary) parser "
            "is added and _PARENT_CIK_KEYS gains a real source column -- bump "
            "EDGE08_PARSER_CAPABILITY_VERSION alongside that change."
        ),
    }


def compute_edge10_audited_by_coverage() -> dict:
    """EDGE-10 AUDITED_BY (company->audit_firm): structural_api_limitation exclusion.

    Confirmed (06-05) that the SEC companyfacts aggregate API never surfaces
    ix:nonNumeric DEI facts (AuditorFirmId/AuditorName/AuditorLocation) for
    any company -- an upstream endpoint-selection gap, not a parser bug. No
    live population evidence needed (the limitation is endpoint-structural,
    not population-dependent); fingerprint is a fixed evidence-version tag,
    stale only when the API's behavior is re-verified under a new version.
    """
    return {
        "status": "excluded",
        "evidence_category": "structural_api_limitation",
        "expected_edge_count": 0,
        "evidence_query_version": "edge10-v1-companyfacts-no-nonnumeric-dei",
        "population_fingerprint": _fingerprint(["edge10-v1-companyfacts-no-nonnumeric-dei"]),
        "review_trigger": (
            "Re-evaluate if SEC's companyfacts API begins surfacing ix:nonNumeric "
            "DEI facts, or if a per-filing inline-XBRL ingestion path is added "
            "(see 06-05-EDGE10-DISPOSITION.md)."
        ),
    }


def compute_deferred_fix_coverage(rel_type_name: str, *, evidence_query_version: str) -> dict:
    """EDGE-09/EDGE-11: valid_zero, not excluded -- root-caused, fix deferred.

    Both share one root cause: `_is_configured_parser_form`
    (warehouse_orchestrator.py) gates the bulk artifact-fetch pipeline to
    OWNERSHIP_FORMS/ADV_FORMS only, so DEF14A/8-K/13F-HR never get
    sec_filing_attachment populated at scale. This is recomputed as
    valid_zero (not a permanent exclusion) every generation: the fingerprint
    is the gate's own governing form sets, imported directly so it can never
    silently drift out of sync with the real gate -- the moment the gate
    widens, the fingerprint changes and this record goes stale.
    """
    from edgar_warehouse.application.warehouse_orchestrator import ADV_FORMS, OWNERSHIP_FORMS

    gate_forms = sorted(OWNERSHIP_FORMS | ADV_FORMS)
    return {
        "status": "valid_zero",
        "evidence_category": "root_caused_fix_deferred",
        "expected_edge_count": 0,
        "evidence_query_version": evidence_query_version,
        "population_fingerprint": _fingerprint(gate_forms),
        "review_trigger": (
            f"Re-evaluate {rel_type_name} once _is_configured_parser_form is widened "
            "to cover its source form family, then deploy + re-fetch + re-derive + "
            "sync + graph-count verify (see 06-PHASE-CLOSURE-LEDGER.md)."
        ),
    }


def compute_relationship_coverage_manifest(
    silver_reader: Any,
    session: Session,
    generation_id: str,
    *,
    relationship_active_counts: Optional[dict[str, int]] = None,
) -> list[dict]:
    """Exhaustive per-generation coverage: exactly one record per active MdmRelationshipType.

    ``relationship_active_counts`` (rel_type_name -> live mdm_active_count,
    e.g. from snowflake_graph.py's relationship_parity payload) supplies the
    real edge count for ``populated`` types; when omitted, populated types
    are still recorded but their expected_edge_count defaults to 1 (nonzero
    placeholder -- callers that need the exact live count should pass it).
    """
    from edgar_warehouse.mdm.database import MdmRelationshipType
    from sqlalchemy import select

    active_counts = relationship_active_counts or {}
    manifest: list[dict] = []
    for rel_type in session.scalars(
        select(MdmRelationshipType).where(MdmRelationshipType.is_active == True)
    ):
        name = rel_type.rel_type_name
        if name in POPULATED_RELATIONSHIP_TYPES:
            count = active_counts.get(name, 1)
            record = {
                "status": "populated",
                "evidence_category": None,
                "expected_edge_count": max(count, 1),
                "evidence_query_version": "populated-v1-live-graph-parity",
                "population_fingerprint": _fingerprint([name, str(count)]),
                "review_trigger": None,
            }
        elif name == "IS_ENTITY_OF":
            record = compute_edge05_is_entity_of_coverage(session)
        elif name == "IS_PERSON_OF":
            record = compute_edge06_is_person_of_coverage(session)
        elif name == "MANAGES_FUND":
            record = compute_edge07_manages_fund_coverage(silver_reader, session)
        elif name == "HAS_PARENT_COMPANY":
            record = compute_edge08_has_parent_company_coverage(session)
        elif name == "AUDITED_BY":
            record = compute_edge10_audited_by_coverage()
        elif name == "EMPLOYED_BY":
            record = compute_deferred_fix_coverage(name, evidence_query_version="edge09-v1-gate-form-set")
        elif name == "INSTITUTIONAL_HOLDS":
            record = compute_deferred_fix_coverage(name, evidence_query_version="edge11-v1-gate-form-set")
        else:
            raise KeyError(
                f"No coverage classification registered for relationship type {name!r}; "
                "every active MdmRelationshipType must be classified (RCOV-01)."
            )
        manifest.append({
            "generation_id": generation_id,
            "rel_type_id": rel_type.rel_type_id,
            "rel_type_name": name,
            **record,
        })
    return manifest


def verify_relationship_coverage_manifest(
    manifest: list[dict],
    active_rel_type_names: Iterable[str],
    *,
    live_active_counts: Optional[dict[str, int]] = None,
    stale_fingerprints: Optional[dict[str, str]] = None,
) -> list[str]:
    """Fail-closed checks (RCOV-01/02). Returns a list of violation strings (empty = pass).

    Checks: every active type present exactly once; no contradictory
    duplicate statuses per type; populated types have a nonzero expected
    count; excluded/valid_zero types have a zero expected count and (when
    live counts are supplied) zero live edges -- a nonzero live count for an
    excluded/valid_zero type means synthetic or unexpected edges exist;
    stale fingerprints (when a freshly recomputed fingerprint is supplied
    and differs from the stored one) block the record.
    """
    violations: list[str] = []
    active_names = set(active_rel_type_names)
    live_counts = live_active_counts or {}
    stale = stale_fingerprints or {}

    by_type: dict[str, list[dict]] = {}
    for record in manifest:
        by_type.setdefault(record["rel_type_name"], []).append(record)

    missing = active_names - set(by_type)
    for name in sorted(missing):
        violations.append(f"missing coverage record for active relationship type {name!r}")

    for name, records in by_type.items():
        if len(records) > 1:
            statuses = {r["status"] for r in records}
            if len(statuses) > 1:
                violations.append(
                    f"contradictory statuses for {name!r} in one generation: {sorted(statuses)}"
                )
                continue
        record = records[0]
        status = record["status"]
        expected = record["expected_edge_count"]

        if status not in RELATIONSHIP_COVERAGE_STATUSES:
            violations.append(f"{name!r} has invalid status {status!r}")
            continue

        if status == "populated" and expected <= 0:
            violations.append(f"{name!r} is marked populated but expected_edge_count is {expected}")

        if status in ("excluded", "valid_zero"):
            if expected != 0:
                violations.append(
                    f"{name!r} is marked {status!r} but expected_edge_count is {expected} (must be 0)"
                )
            live_count = live_counts.get(name)
            if live_count is not None and live_count != 0:
                violations.append(
                    f"{name!r} is marked {status!r} but has {live_count} live edge(s) -- "
                    "synthetic or unexpected data for an excluded/valid-zero type"
                )

        if name in stale and stale[name] != record["population_fingerprint"]:
            violations.append(
                f"{name!r} coverage fingerprint is stale (stored {record['population_fingerprint']!r} "
                f"!= freshly recomputed {stale[name]!r}); recompute before activation"
            )

    return violations
