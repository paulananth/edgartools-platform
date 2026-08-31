"""Declares which table(s) stand as evidence for each of the six case
categories the DuckDB Retirement Cutover map's own validation-standard
decision names ("routing-band, volume, boundary, parser, no-op, and
guarded-publication cases," mirroring the existing MaxConcurrency4 Data
Integrity Evidence precedent's case-selection shape).

Those six categories were coined for a *same-store* BatchSilver rerun
(different concurrent writers racing one shared DuckDB object). This tool
compares two different stores (DuckDB canonical vs. Snowflake
``EDGARTOOLS_SILVER``), so two of the six categories do not carry over
unchanged -- rather than force a fabricated mapping, this module states
plainly which ones transfer and which do not, and why.

- **routing_band**: which domain "family" a table belongs to (company-
  anchored root data, ownership filings, ADV filings, 13F, financial facts)
  -- carries over directly as "at least one table per family is checked."
  This tool checks *every* table in every family every run, so this
  category is satisfied trivially and by construction, not by a special
  case.
- **volume**: carries over directly -- ``sec_thirteenf_holding`` (~6.8M
  rows, confirmed live) is the mandated large-scale case; a small table is
  the contrasting low-volume case.
- **boundary**: carries over, redefined for this context -- not a batch
  window edge, but the first/last row by declared primary-key ordering
  within a table's compared cohort. Handled inside
  ``sql_checks.fetch_key_cohort`` for every table's cohort, not a
  separate table-level case.
- **parser**: carries over directly -- a table whose row count legitimately
  varies by parser output (an ``optional_or_many``-cardinality table) is
  named explicitly as evidence that the tool's legitimate-zero handling is
  exercised, not just declared.
- **no_op**: redefined for this context. The original meaning ("an
  already-loaded batch re-processes with zero effective writes") doesn't
  apply to a read-only cross-store comparison tool -- there is no write
  path here to no-op. The nearest honest analogue is *this tool's own
  idempotency*: re-running it against an unchanged Snowflake watermark
  should reproduce identical digests. ``report.py``'s ``--compare-to``
  flag makes this checkable directly (two real invocations, not simulated)
  rather than asserted.
- **guarded_publication**: **does not transfer**. It named BatchSilver's
  shared-object ETag-guarded promotion race (concurrent writers contending
  for one S3 object) -- a write-path concurrency concern with no analogue
  in a read-only, single-writer-per-store comparison. Declared here as
  explicitly out of scope for this tool rather than silently dropped or
  fabricated, per this map's own established pattern (Tickets 06/07) of
  calling out where an inherited framing doesn't survive contact with a
  different context.
"""
from __future__ import annotations

from dataclasses import dataclass

# Table chosen as the mandated large-scale case (Ticket 08's own explicit
# requirement) -- confirmed live at ~6.8M rows (CLAUDE.md's "MDM Postgres
# migration-011" entry and this ticket's own text).
VOLUME_LARGE_TABLE = "sec_thirteenf_holding"
# A genuinely small table for contrast (single-digit-CRD-keyed snapshot
# data, not filing-volume-driven).
VOLUME_SMALL_TABLE = "sec_pcaob_firm_identity"

ROUTING_BAND_TABLES = {
    "company_root": "sec_company",
    "ownership": "sec_ownership_non_derivative_txn",
    "adv": "sec_adv_private_fund",
    "thirteenf": "sec_thirteenf_holding",
    "financial": "sec_financial_fact",
}

# A table whose row count legitimately varies by parser output -- not every
# ownership filing reports a derivative transaction.
PARSER_OPTIONAL_TABLE = "sec_ownership_derivative_txn"


@dataclass(frozen=True)
class CaseCoverage:
    routing_band: dict[str, str]
    volume_large: str
    volume_small: str
    parser_optional: str
    boundary_note: str
    no_op_note: str
    guarded_publication_note: str


def build_case_coverage() -> CaseCoverage:
    return CaseCoverage(
        routing_band=dict(ROUTING_BAND_TABLES),
        volume_large=VOLUME_LARGE_TABLE,
        volume_small=VOLUME_SMALL_TABLE,
        parser_optional=PARSER_OPTIONAL_TABLE,
        boundary_note=(
            "covered per-table inside every cohort selection (min/max key by "
            "declared primary-key ordering), not a separate case table"
        ),
        no_op_note=(
            "not asserted within a single run -- pass --compare-to a prior "
            "report.json to check this tool's own rerun idempotency against an "
            "unchanged Snowflake watermark"
        ),
        guarded_publication_note=(
            "does not transfer to a read-only cross-store comparison tool -- "
            "see this module's docstring"
        ),
    )
