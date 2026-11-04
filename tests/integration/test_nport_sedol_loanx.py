"""A SEDOL and a LoanX join the Security their holding already keys (ticket 125).

The real chain on invented holdings (the holdings extract with the `isin`, `sedol` and `loanx`
pair sets, reduce.yaml, combine.yaml, mdm.prepare and the Dataset Contract's records): a holding
keyed by its CUSIP, or by its ISIN when it has none, that files one SEDOL or one LoanX gives
its Security that identifier; two values on one Security are both kept; a holding with neither
a CUSIP nor an ISIN makes no Security (ticket 190 would). Invented values only.
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
HOLDINGS = [["A-1", "1", "Example Corp", "", "Note", CUSIP],        # CUSIP and a SEDOL
            ["A-1", "2", "Example Corp", "", "Note", CUSIP],        # the same CUSIP, a second SEDOL
            ["A-1", "3", "Other Inc", "", "Loan", CUSIP_TWO],       # CUSIP and a LoanX
            ["A-1", "4", "Third Ltd", "", "Note", ""],              # no CUSIP: keyed by its ISIN, with a SEDOL
            ["A-1", "5", "Fourth Ltd", "", "Note", ""]]             # no CUSIP, no ISIN: only a SEDOL
SEDOLS = [["1", SEDOL], ["2", SEDOL_TWO], ["4", SEDOL], ["5", SEDOL_TWO]]
LOANXS = [["3", LOANX]]
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


def test_a_holding_with_neither_cusip_nor_isin_makes_no_security(tmp_path):
    keys = {r["provenance"]["record_key"] for r in prepared_records(tmp_path)}
    assert keys == {CUSIP, CUSIP_TWO, ISIN}
