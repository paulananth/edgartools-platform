"""The committed registration reading (ticket 149) on an invented page, from inside a capture snapshot as
`provider.capture` keeps it: the offering terms the cover states and the valuation statement lines, with the
accession number and CIK taken from the snapshot's own metadata. Every name and number here is invented."""
import io
import json
import zipfile
from pathlib import Path

import yaml

from edgar_warehouse.rules.source_engine import SourceEngine

CONTRACT = yaml.safe_load((Path(__file__).parents[2] / "rules/sources/sec.registration/registration-page.yaml").read_text())

PAGE = ("<html><head><title>Invented Holdings Inc. Form S-1</title></head><body>"
        "<p>Invented Holdings Inc.</p><p>2,500,000 Shares of Common Stock</p>"
        "<p>The initial public offering price is expected to be between $14.00 and $16.00 per share. "
        "We have applied to list on the Nasdaq Capital Market under the symbol \"INVT\".</p>"
        "<p>The underwriters have an option to purchase up to 375,000 additional shares of common stock.</p>"
        "<p>CONSOLIDATED BALANCE SHEETS</p><p>(in thousands)</p>"
        "<table><tr><td></td><td>December 31, 2025</td><td></td><td>December 31, 2024</td></tr>"
        "<tr><td>Cash and cash equivalents</td><td>$</td><td>1,234</td><td>$</td><td>987</td></tr>"
        "<tr><td>Total assets</td><td>$</td><td>9,000</td><td>$</td><td>(56</td><td>)</td></tr>"
        "<tr><td>Prepaid expenses</td><td>3</td><td>4</td></tr></table>"
        "<p>CONSOLIDATED STATEMENTS OF OPERATIONS</p>"
        "<table><tr><td></td><td>2025</td><td>2024</td></tr>"
        "<tr><td>Revenues</td><td>$ 5,000</td><td>$ 4,000</td></tr>"
        "<tr><td>Net loss</td><td>(2,000)</td><td>(1,500)</td></tr></table></body></html>")


def snapshot(page: str, metadata: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("metadata.json", json.dumps(metadata))
        archive.writestr("payload", page.encode())
    return out.getvalue()


def read(page: str = PAGE):
    metadata = {"scope": {"accession": "0000000000-26-000001", "cik": "0000000001"},
                "captured_at": "2026-10-30T11:27:18.747439+00:00"}
    return SourceEngine(CONTRACT).read(snapshot(page, metadata)).tables


def test_the_cover_terms_are_found_and_the_snapshot_names_the_filing():
    (offering,) = read()["offering"]
    assert (offering["accession_number"], offering["cik"]) == ("0000000000-26-000001", "0000000001")
    assert offering["captured_at"] == "2026-10-30T11:27:18.747439+00:00"  # the moment the snapshot was taken
    assert (offering["shares_offered"], offering["price_low"], offering["price_high"]) == ("2500000", "14.00", "16.00")
    assert (offering["ticker"], offering["exchange"], offering["over_allotment_shares"]) == ("INVT", "Nasdaq Capital Market", "375000")
    assert offering["price_fixed"] is None  # a range, not a fixed price


def test_a_cover_that_states_nothing_gives_empty_terms_not_zero():
    (offering,) = read("<html><body><p>Invented Holdings Inc.</p></body></html>")["offering"]
    assert [offering[k] for k in ("shares_offered", "price_low", "ticker", "exchange", "over_allotment_shares")] == [None] * 5


def test_valuation_lines_carry_their_numbers_statement_scale_and_years():
    lines = {line["label"]: line for line in read()["statement_line"]}
    assert set(lines) == {"Cash and cash equivalents", "Total assets", "Revenues", "Net loss"}  # prepaid is no line item
    cash = lines["Cash and cash equivalents"]
    assert (cash["line_item"], cash["statement"], cash["scale"]) == ("cash", "balance_sheet", "thousands")
    assert (cash["value1"], cash["value2"], cash["year1"], cash["year2"]) == ("1234", "987", "2025", "2024")
    assert lines["Total assets"]["value2"] == "56" and lines["Total assets"]["value2_negative"] is True
    revenue, loss = lines["Revenues"], lines["Net loss"]
    assert (revenue["statement"], revenue["scale"], revenue["value1"], revenue["value2"]) == ("income_statement", None, "5000", "4000")
    assert (loss["line_item"], loss["value1"], loss["value1_negative"], loss["value2"]) == ("net_income", "2000", True, "1500")
