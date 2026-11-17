"""The committed final-prospectus reading on an invented page, from inside a capture snapshot as
`provider.capture` keeps it: the cover's final terms, its price lines per share and in total, and the
underwriters with their shares. Every name and number here is invented."""
from pathlib import Path

import yaml

from edgar_warehouse.rules.source_engine import SourceEngine
from tests.engine.test_registration_page_reading import snapshot

CONTRACT = yaml.safe_load((Path(__file__).parents[2] / "rules/sources/sec.prospectus/prospectus-page.yaml").read_text())

PAGE = ("<html><head><title>Invented Rockets Inc. 424(b)(4)</title></head><body>"
        "<p>Filed Pursuant to Rule 424(b)(4)</p><p>12,000,000 Shares</p><p>Invented Rockets Inc.</p>"
        "<p>We are offering 12,000,000 shares of our Class A common stock. The initial public offering price is $21.00 per share."
        " We have been approved to list our Class A common stock on The Nasdaq Stock Market LLC under</p>"
        "<p>the symbol “INVR.”</p>"
        "<table><tr><td></td><td>Per Share</td><td>Total</td></tr>"
        "<tr><td>Initial public offering price ..........</td><td>$21.00</td><td>$252,000,000</td></tr>"
        "<tr><td>Underwriting discounts and commissions(1) ....</td><td>$</td><td>1.47</td><td>$</td><td>17,640,000</td></tr>"
        "<tr><td>Proceeds, before expenses, to Invented Rockets Inc. ....</td><td>$19.53</td><td>$234,360,000</td></tr></table>"
        "<p>The underwriters may also exercise an option to purchase up to an additional 1,800,000 shares of our Class A common stock.</p>"
        "<p>Underwriting</p>"
        "<table><tr><td>Name</td><td>Number of Shares</td></tr>"
        "<tr><td>Example Securities LLC (1) ........</td><td>7,000,000</td></tr>"
        "<tr><td>Sample Capital Markets, Inc. ......</td><td>5,000,000</td></tr>"
        "<tr><td>Total ........</td><td>12,000,000</td></tr></table>"
        "<p>Initial public offering price per share</p>"
        "<table><tr><td>Initial public offering price per share ....</td><td>$21.00</td></tr></table>"
        "</body></html>")


def read(page: str = PAGE):
    metadata = {"scope": {"accession_number": "0000000000-26-000002", "cik": "0000000002"},
                "captured_at": "2026-11-17T15:00:00+00:00"}
    return SourceEngine(CONTRACT).read(snapshot(page, metadata)).tables


def test_the_cover_states_the_final_terms_and_the_snapshot_names_the_filing():
    (offering,) = read()["offering"]
    assert (offering["accession_number"], offering["cik"]) == ("0000000000-26-000002", "0000000002")
    assert (offering["shares_offered"], offering["price_per_share"], offering["over_allotment_shares"]) == (
        "12000000", "21.00", "1800000")
    assert (offering["ticker"], offering["exchange"]) == ("INVR", "Nasdaq Stock Market")


def test_the_price_lines_carry_their_amount_per_share_and_in_total():
    lines = {line["line"]: (line["per_share"], line["total"]) for line in read()["cover_line"]}
    assert lines == {"offering_price": ("21.00", "252000000"), "underwriting_discount": ("1.47", "17640000"),
                     "proceeds": ("19.53", "234360000")}  # the dilution table's per-share price is not a cover line


def test_each_underwriter_is_named_with_its_shares_and_the_heading_and_total_are_not():
    assert [(u["underwriter"], u["shares"]) for u in read()["underwriter"]] == [
        ("Example Securities LLC", "7000000"), ("Sample Capital Markets, Inc.", "5000000")]


def test_a_page_that_states_nothing_gives_empty_terms_not_zero():
    tables = read("<html><body><p>Invented Rockets Inc.</p></body></html>")
    (offering,) = tables["offering"]
    assert [offering[k] for k in ("shares_offered", "price_per_share", "ticker", "exchange", "over_allotment_shares")] == [None] * 5
    assert tables.get("cover_line", []) == tables.get("underwriter", []) == []
