"""N-PORT's facts on the Security master (ticket 138; operator, 2026-10-25:
"Most-filed value"; 2026-10-28: "all master data fields must be on mdm").

Every holding repeats six facts about its Security: asset category, issuer
type, investment country, currency, restricted and derivative category. The
Security's record takes, for each, the value the most holdings of it file; a
tie keeps none, and a holding filing none votes for none. The holding's silver
row does not repeat them (one system of record, ticket 143). Values are
invented look-alikes, through the real chain (source.yaml, reduce.yaml,
combine.yaml, record.yaml and the Dataset Contract).
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from tests.integration import test_nport_link_start as chain

COLUMNS = [*chain.COLUMNS, "ASSET_CAT", "ISSUER_TYPE", "INVESTMENT_COUNTRY", "CURRENCY_CODE",
           "IS_RESTRICTED_SECURITY", "DERIVATIVE_CAT"]
HELD, BARE = "ZZ0000013", "ZZ0000021"
HOLDINGS = [
    ["A-1", "1", "Example Corp", chain.LEI, "Common", HELD, "EC", "CORP", "US", "USD", "N", ""],
    ["A-1", "2", "Example Corp", chain.LEI, "Common", HELD, "EC", "CORP", "US", "USD", "N", ""],
    ["A-2", "3", "Example Corp", chain.LEI, "Common", HELD, "DBT", "MUN", "US", "EUR", "N", ""],
    ["A-2", "4", "Example Corp", chain.LEI, "Common", HELD, "", "MUN", "", " usd", "Y", ""],
    ["A-1", "5", "Other Inc", "", "Common", BARE, "", "", "", "", "", ""],
]


def records(root: Path) -> dict[str, dict]:
    store = Artifacts()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "nport.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("FUND_REPORTED_HOLDING.tsv", "\n".join("\t".join(r) for r in [COLUMNS, *HOLDINGS]) + "\n")
        z.writestr("IDENTIFIERS.tsv", "HOLDING_ID\tIDENTIFIER_ISIN\n")
        z.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\tFILING_DATE\n"
                   + "".join(f"{a}\t{d}\n" for a, d in chain.FILINGS.items()))
    raw = store.put_bytes((root / "capture.zip").as_uri(), path.read_bytes())
    holdings = chain.read(store, root / "holdings", "source.yaml", raw, chain.Q2, lookups={"isin": []})
    issuers = chain.issuers(store, root, raw, [], chain.Q2)
    found = chain.security_records(store, root, holdings, issuers, batch_id="facts")
    # A field is a patch: a stated value, or `unknown` when none is kept.
    return {r["provenance"]["record_key"]: {k: f.get("value") if f.get("op") == "value" else None
                                            for k, f in r["fields"].items()} for r in found}


def test_each_fact_is_the_value_the_most_holdings_file_and_a_tie_keeps_none(tmp_path):
    fields = records(tmp_path)
    # EC 2 to DBT 1 (one files none); CORP 2 to MUN 2 is a tie; US 3; USD 3 to EUR 1
    # (" usd" is USD: each value is trimmed and upper-cased);
    # N 3 to Y 1; no holding files a derivative category.
    assert {k: fields[HELD].get(k) for k in ("asset_category", "issuer_type", "investment_country",
                                             "currency", "restricted", "derivative_category")} == {
        "asset_category": "EC", "issuer_type": None, "investment_country": "US",
        "currency": "USD", "restricted": "N", "derivative_category": None}


def test_a_security_whose_holdings_file_no_fact_has_none(tmp_path):
    fields = records(tmp_path)
    assert not {"asset_category", "issuer_type", "investment_country", "currency", "restricted",
                "derivative_category"} & {k for k, v in fields[BARE].items() if v is not None}
