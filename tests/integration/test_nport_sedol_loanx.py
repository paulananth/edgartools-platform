"""A SEDOL and a LoanX join the Security their holding already keys (ticket 125).

The real chain on invented holdings (the holdings extract with the `isin`, `sedol` and `loanx`
pair sets, reduce.yaml, combine.yaml, mdm.prepare and the Dataset Contract's records): a holding
keyed by its CUSIP, or by its ISIN when it has none, that files one SEDOL or one LoanX gives
its Security that identifier; two values on one Security are both kept; a holding with neither
a CUSIP nor an ISIN is keyed by its ISIN, else its SEDOL, else its LoanX (ticket 190; one shared
path, so a class is a line of configuration and a test). Invented values only.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from tests.integration import test_nport_link_start as cusip

CUSIP, CUSIP_TWO = "ZZ0000013", "ZZ0000021"  # invented, check digits valid
ISIN = "ZZ0000000016"  # invented, check digit valid
SEDOL, SEDOL_TWO, LOANX = "C000008", "B000009", "LX000001"  # invented, SEDOL check digits valid
SEDOL_ALONE, LOANX_ALONE = "D000007", "LX000002"  # on holdings with no CUSIP and no ISIN
HOLDINGS = [["A-1", "1", "Example Corp", "", "Note", CUSIP],        # CUSIP and a SEDOL
            ["A-1", "2", "Example Corp", "", "Note", CUSIP],        # the same CUSIP, a second SEDOL
            ["A-1", "3", "Other Inc", "", "Loan", CUSIP_TWO],       # CUSIP and a LoanX
            ["A-1", "4", "Third Ltd", "", "Note", ""],              # no CUSIP: keyed by its ISIN, with a SEDOL
            ["A-1", "5", "Fourth Ltd", "", "Note", ""],             # no CUSIP, no ISIN: only a SEDOL
            ["A-1", "6", "Fourth Ltd", "", "Note", ""],             # the same SEDOL again: the same Security
            ["A-1", "7", "Fifth Ltd", "", "Loan", ""]]              # no CUSIP, no ISIN: only a LoanX
SEDOLS = [["1", SEDOL], ["2", SEDOL_TWO], ["4", SEDOL], ["5", SEDOL_ALONE], ["6", SEDOL_ALONE]]
LOANXS = [["3", LOANX], ["7", LOANX_ALONE]]
ISINS = [["4", ISIN]]


def prepared_records(root: Path) -> list[dict]:
    store = Artifacts()
    root.mkdir(parents=True, exist_ok=True)
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as z:
        z.writestr("FUND_REPORTED_HOLDING.tsv", "\n".join("\t".join(r) for r in [cusip.COLUMNS, *HOLDINGS]) + "\n")
        z.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\tFILING_DATE\nA-1\t05-JUN-2026\n")
    raw = store.put_bytes((root / "capture.zip").as_uri(), body.getvalue())
    holdings = cusip.read(store, root / "holdings", "source.yaml", raw, cusip.Q2,
                          lookups={"isin": ISINS, "sedol": SEDOLS, "loanx": LOANXS})
    issuers = cusip.issuers(store, root, raw, ISINS, cusip.Q2)
    return cusip.security_records(store, root, holdings, issuers, batch_id="check-sedol-loanx")


def test_a_sedol_and_a_loanx_join_the_security_their_holding_keys(tmp_path):
    found = {r["provenance"]["record_key"]: r["identifiers"] for r in prepared_records(tmp_path)}
    assert found[CUSIP]["cusip"] == CUSIP
    assert sorted(found[CUSIP]["sedol"]) == sorted([SEDOL, SEDOL_TWO])
    assert found[CUSIP_TWO]["loanx"] == [LOANX]
    assert found[ISIN]["isin"] == ISIN and found[ISIN]["sedol"] == [SEDOL]


def test_a_holding_with_no_cusip_and_no_isin_is_keyed_by_its_sedol_or_its_loanx(tmp_path):
    made = prepared_records(tmp_path)
    records = {r["provenance"]["record_key"]: r for r in made}
    assert set(records) == {CUSIP, CUSIP_TWO, ISIN, SEDOL_ALONE, LOANX_ALONE} and len(made) == 5
    # Two holdings filing the same SEDOL are one Security, whose key is the one class it files.
    assert records[SEDOL_ALONE]["identifiers"] == {"sedol": SEDOL_ALONE}
    assert records[LOANX_ALONE]["identifiers"] == {"loanx": LOANX_ALONE}


def test_a_holding_with_a_cusip_or_an_isin_keeps_that_key_whatever_else_it_files(tmp_path):
    records = {r["provenance"]["record_key"]: r for r in prepared_records(tmp_path)}
    assert records[CUSIP]["identifiers"]["cusip"] == CUSIP and CUSIP in records
    assert records[ISIN]["identifiers"]["isin"] == ISIN and records[ISIN]["identifiers"]["sedol"] == [SEDOL]
    assert SEDOL not in records  # a SEDOL filed beside a CUSIP or an ISIN joins; it never keys
