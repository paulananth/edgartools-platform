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


# mdm-company-person-contamination ticket 01 (2026-09-07): forms an
# individual reporting owner can file about themselves -- Section 16
# (beneficial ownership by insiders: 3/4/5/144) and Section 13 (beneficial
# ownership generally, incl. activist investors: 13D/13G, both SEC
# spellings) plus DFAN14A (proxy-contest participant filing, also filable
# by an individual). A CIK whose ENTIRE sec_company_filing history is
# confined to this set has never filed as a real operating registrant or
# institutional manager -- validated live against 6 known examples (3
# companies, 3 individuals, 6/6 correct) and a 300-CIK random sample
# (~37% classified as individual-only, consistent with two independent
# signals: a name-keyword sweep at ~44% and an owner_cik cross-reference
# lower bound at ~13%).
INDIVIDUAL_ONLY_OWNERSHIP_FORMS = frozenset({
    "3", "3/A", "4", "4/A", "5", "5/A", "144", "144/A",
    "SC 13D", "SC 13D/A", "SCHEDULE 13D", "SCHEDULE 13D/A",
    "SC 13G", "SC 13G/A", "SCHEDULE 13G", "SCHEDULE 13G/A",
    "DFAN14A",
})


def exclude_individual_reporting_owners_sql(cik_column: str = "cik") -> str:
    """WHERE-clause fragment excluding CIKs that are individual reporting
    owners, not real companies -- see INDIVIDUAL_ONLY_OWNERSHIP_FORMS.

    A CIK with NO sec_company_filing rows at all (never seen as either
    side of a filing) is NOT excluded here -- absence of filing history
    isn't evidence of being an individual, and run_companies' own callers
    already handle a missing/empty silver row separately.

    `cik_column` lets a caller qualify the column (e.g. "sc.cik") when the
    surrounding query aliases sec_company; the subquery's own `cik` column
    is always unqualified since it's scoped to its own FROM clause.
    """
    forms_list = ", ".join(f"'{f}'" for f in sorted(INDIVIDUAL_ONLY_OWNERSHIP_FORMS))
    return f"""{cik_column} NOT IN (
        SELECT cik FROM sec_company_filing
        GROUP BY cik
        HAVING COUNT_IF(form NOT IN ({forms_list})) = 0
    )"""
