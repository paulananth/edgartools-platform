"""Per-table reconciliation contracts for the DuckDB Retirement Cutover
(Ticket 08): declares, for every SEC-content table this cutover touches,
what "bronze-to-silver key expectations," "declared primary-key uniqueness,"
"required-parent integrity," and "canonical semantic-content digest" mean
concretely -- reusing this repo's existing Production Release Readiness
vocabulary (CONTEXT.md, ``docs/release-readiness/maxconcurrency4-data-
integrity-proof.md``) rather than inventing a parallel one.

Table universe: every key of ``PROTECTED_TABLE_REGISTRY``
(``edgar_warehouse/silver_protection.py``) except ``pipeline_run_lease`` --
that one table is run-level concurrency bookkeeping, not SEC content (same
"10 bookkeeping tables are a different concern" boundary Ticket 08's own
spec draws against Ticket 02's scope). ``business_keys``/``authority_column``/
``provenance_columns`` are taken directly from that registry rather than
re-declared here -- it is already this repo's fail-closed source of truth
for per-table key/provenance semantics (silver_protection.py's own docstring:
"Fail-closed protected-table registry").

Parent-link declarations below are informed by
``edgar_warehouse/application/commands/validate_data_quality.py``'s
``_FK_CHECKS`` list (an independently reviewed, already-live orphan-check
declaration for 18 of these 30 tables) -- re-declared here rather than
imported, since that list is private to a QA-gate module with a narrower
table scope than this ticket's, and this module's own additions (the 12
tables validate_data_quality.py does not cover: sec_current_filing_feed,
sec_adv_filing, sec_adv_firm_roster, sec_subsidiary_evidence,
sec_auditor_report_evidence, sec_pcaob_firm_identity, sec_raw_object,
sec_company (root, no parent), sec_thirteenf_filing, sec_employment_event,
sec_guidance_fact, and sec_filing_attachment's own bronze_anchor) needed
the same relationships derived and cross-checked anyway. Every entry below
where the two lists overlap was verified to agree with
``_FK_CHECKS`` before being written down.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from edgar_warehouse.silver_protection import PROTECTED_TABLE_REGISTRY

Cardinality = Literal["required", "optional_or_many"]
"""``"required"``: every parent-key row is expected to produce >=1 child row
-- absence is a defect, not a legitimate outcome. ``"optional_or_many"``:
zero child rows for a given parent key is a legitimate outcome (a parser
that only sometimes produces output, or produces a variable count) --
mirrors the Table-Specific Reconciliation standard's own "explicit
legitimate-zero outcomes for optional and one-to-many parsers" language.
"""


@dataclass(frozen=True)
class ParentLink:
    """One required-parent relationship: every non-null value of
    ``(child_table.child_column)`` must exist as ``(parent_table.parent_column)``.
    Composite-key parents are not needed here -- every relationship in this
    domain resolves via a single shared column (``cik`` or
    ``accession_number``).
    """

    child_table: str
    child_column: str
    parent_table: str
    parent_column: str


@dataclass(frozen=True)
class TableContract:
    """Declares how one table's four Table-Specific Reconciliation checks
    are computed.

    ``bronze_anchor``: the immediate bronze-adjacent table proving this
    row traces back to a real, captured SEC record ("bronze-to-silver key
    expectations"). For every table below this is either ``sec_company``
    (cik-anchored root data) or ``sec_company_filing`` (accession-anchored
    filing content) -- both of those, and every other declared root
    (``sec_adv_filing``, ``sec_thirteenf_filing``, ``sec_current_filing_feed``,
    ``sec_adv_firm_roster``, ``sec_pcaob_firm_identity``, ``sec_raw_object``),
    have ``bronze_anchor=None`` -- they *are* the bronze-adjacent anchor for
    their own family, not children of one.

    ``logical_parent``: the table's immediate domain parent for "required-
    parent integrity." Often identical to ``bronze_anchor`` (most tables
    hang directly off a filing); explicitly different where a table has a
    closer parent in the same family (e.g. ``sec_ownership_non_derivative_txn``
    -> ``sec_ownership_reporting_owner``, not straight to
    ``sec_company_filing``; ``sec_adv_office`` -> ``sec_adv_filing``, not
    ``sec_company_filing``, since ADV filings are not tracked in
    ``sec_company_filing`` at all).

    ``cardinality``: see ``Cardinality`` above.
    """

    table_name: str
    business_keys: tuple[str, ...]
    bronze_anchor: ParentLink | None
    logical_parent: ParentLink | None
    cardinality: Cardinality
    authority_column: str | None
    semantic_exclude_columns: frozenset[str]


def _link(child_table: str, child_column: str, parent_table: str, parent_column: str) -> ParentLink:
    return ParentLink(child_table, child_column, parent_table, parent_column)


# child_table -> (bronze_anchor, logical_parent, cardinality)
# A `None` bronze_anchor/logical_parent means "this table is a root for its
# own family" -- not a gap, a deliberate declaration (see TableContract
# docstring above). Every entry with a non-None bronze_anchor was chosen
# because a captured/discovered SEC record (a filing, or the company itself)
# must exist before this table's row can legitimately exist.
_TABLE_RELATIONSHIPS: dict[str, tuple[ParentLink | None, ParentLink | None, Cardinality]] = {
    "sec_company": (None, None, "required"),
    "sec_company_address": (_link("sec_company_address", "cik", "sec_company", "cik"), None, "optional_or_many"),
    "sec_company_former_name": (
        _link("sec_company_former_name", "cik", "sec_company", "cik"),
        None,
        "optional_or_many",
    ),
    "sec_company_submission_file": (
        _link("sec_company_submission_file", "cik", "sec_company", "cik"),
        None,
        "optional_or_many",
    ),
    "sec_company_filing": (
        _link("sec_company_filing", "cik", "sec_company", "cik"),
        None,
        "required",
    ),
    "sec_company_ticker": (
        _link("sec_company_ticker", "cik", "sec_company", "cik"),
        None,
        "optional_or_many",
    ),
    # Raw daily-index feed row -- may legitimately precede sec_company_filing
    # (it is often the trigger that creates it). No parent declared rather
    # than guessing a relationship that could invert cause and effect.
    "sec_current_filing_feed": (None, None, "required"),
    "sec_ownership_reporting_owner": (
        _link("sec_ownership_reporting_owner", "accession_number", "sec_company_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    "sec_ownership_non_derivative_txn": (
        _link("sec_ownership_non_derivative_txn", "accession_number", "sec_company_filing", "accession_number"),
        _link(
            "sec_ownership_non_derivative_txn", "accession_number", "sec_ownership_reporting_owner", "accession_number"
        ),
        "optional_or_many",
    ),
    "sec_ownership_derivative_txn": (
        _link("sec_ownership_derivative_txn", "accession_number", "sec_company_filing", "accession_number"),
        _link(
            "sec_ownership_derivative_txn", "accession_number", "sec_ownership_reporting_owner", "accession_number"
        ),
        "optional_or_many",
    ),
    # ADV filings are not tracked in sec_company_filing at all (a separate
    # investment-adviser universe) -- this table is the root of its own
    # family, same as sec_company_filing is for operating companies.
    "sec_adv_filing": (None, None, "required"),
    "sec_adv_office": (
        _link("sec_adv_office", "accession_number", "sec_adv_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    "sec_adv_disclosure_event": (
        _link("sec_adv_disclosure_event", "accession_number", "sec_adv_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    "sec_adv_private_fund": (
        _link("sec_adv_private_fund", "accession_number", "sec_adv_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    # Periodic CRD-keyed roster snapshot, independent of the filing universe.
    "sec_adv_firm_roster": (None, None, "required"),
    "sec_subsidiary_evidence": (
        _link("sec_subsidiary_evidence", "accession_number", "sec_company_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    "sec_auditor_report_evidence": (
        _link("sec_auditor_report_evidence", "accession_number", "sec_company_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    # PCAOB firm registry snapshot -- standalone reference data.
    "sec_pcaob_firm_identity": (None, None, "required"),
    # Content-addressed store, standalone by design (silver_protection.py's
    # own comment: raw_object_id IS the sha256 of the fetched bytes; the
    # real content<->filing linkage lives in sec_filing_attachment).
    "sec_raw_object": (None, None, "required"),
    "sec_filing_attachment": (
        _link("sec_filing_attachment", "accession_number", "sec_company_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    "sec_filing_text": (
        _link("sec_filing_text", "accession_number", "sec_company_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    "sec_financial_fact": (
        _link("sec_financial_fact", "accession_number", "sec_company_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    "sec_financial_derived": (
        _link("sec_financial_derived", "accession_number", "sec_company_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    "sec_earnings_release": (
        _link("sec_earnings_release", "accession_number", "sec_company_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    "sec_accounting_flag": (
        _link("sec_accounting_flag", "accession_number", "sec_company_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    "sec_executive_record": (
        _link("sec_executive_record", "accession_number", "sec_company_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    "sec_thirteenf_holding": (
        _link("sec_thirteenf_holding", "accession_number", "sec_company_filing", "accession_number"),
        _link("sec_thirteenf_holding", "accession_number", "sec_thirteenf_filing", "accession_number"),
        "optional_or_many",
    ),
    "sec_thirteenf_filing": (
        _link("sec_thirteenf_filing", "accession_number", "sec_company_filing", "accession_number"),
        None,
        "required",
    ),
    "sec_employment_event": (
        _link("sec_employment_event", "accession_number", "sec_company_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
    "sec_guidance_fact": (
        _link("sec_guidance_fact", "accession_number", "sec_company_filing", "accession_number"),
        None,
        "optional_or_many",
    ),
}

# Tables excluded from PROTECTED_TABLE_REGISTRY for this ticket's purposes:
# run-level concurrency bookkeeping, not SEC content (Ticket 08's own spec
# note: "Confirmed disjoint from Ticket 02's scope").
_EXCLUDED_FROM_TARGET_SET = frozenset({"pipeline_run_lease"})


def _build_table_contracts() -> dict[str, TableContract]:
    contracts: dict[str, TableContract] = {}
    for table_name, policy in PROTECTED_TABLE_REGISTRY.items():
        if table_name in _EXCLUDED_FROM_TARGET_SET:
            continue
        bronze_anchor, logical_parent, cardinality = _TABLE_RELATIONSHIPS[table_name]
        exclude = set(policy.provenance_columns)
        if policy.authority_column:
            # The authority column itself is compared separately (it's the
            # freshness watermark this tool scopes cross-store comparison
            # by, per the semantic-digest freshness-skew note in
            # collector.py) -- not part of the semantic-content digest.
            exclude.add(policy.authority_column)
        contracts[table_name] = TableContract(
            table_name=table_name,
            business_keys=policy.business_keys,
            bronze_anchor=bronze_anchor,
            logical_parent=logical_parent,
            cardinality=cardinality,
            authority_column=policy.authority_column,
            semantic_exclude_columns=frozenset(exclude),
        )
    missing = set(_TABLE_RELATIONSHIPS) - set(contracts)
    extra = set(contracts) - set(_TABLE_RELATIONSHIPS)
    if missing or extra:
        raise AssertionError(
            "table_reconciliation.contracts: _TABLE_RELATIONSHIPS and "
            f"PROTECTED_TABLE_REGISTRY have drifted apart -- missing={missing} extra={extra}"
        )
    return contracts


TABLE_CONTRACTS: dict[str, TableContract] = _build_table_contracts()
