"""Shared SQL fragment helpers for MDM's sec_company_filing join sites.

Same "no dependency on either side of the pipeline.py <-> application
circular import" shape as bounded_fetch.py -- extracted so `pipeline.py`
and `relationship_bulk_load.py` can both reuse the identical
issuer-disambiguation text instead of typing it out separately at every
call site.
"""
from __future__ import annotations


def prefer_non_owner_cik_qualify(partition_cols: str) -> str:
    """QUALIFY clause resolving one sec_company_filing row per ownership row.

    duckdb-retirement-cutover Ticket 16 (2026-09-06): sec_company_filing
    now widens to one row per (accession_number, cik) for a multi-CIK
    accession (ownership filings list both the issuer's and the individual
    reporting owner's own CIK; co-registrant filings list two real
    companies). A join from an ownership row (which carries its own
    owner_cik) to sec_company_filing (aliased `f` at every call site) can
    therefore match more than once for a widened accession -- once
    correctly to the issuer's cik, and once to the reporting owner's own
    cik, which is self-referential and wrong.

    This clause prefers whichever candidate's cik is NOT this row's own
    owner_cik, falling back to whatever single match exists when that's
    the only candidate -- so a previously-working single-match case (the
    ~99% unaffected single-CIK accession, or a genuinely untracked issuer)
    never regresses to no match at all.

    `partition_cols` is the natural key identifying one ownership row at
    each call site (e.g. "o.accession_number, o.owner_index" or
    "t.accession_number, t.owner_index, t.txn_index") -- the only thing
    that varies between call sites; the disambiguation rule itself never
    does.
    """
    return f"""
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY {partition_cols}
                ORDER BY CASE WHEN f.cik = o.owner_cik THEN 1 ELSE 0 END
            ) = 1
        """
