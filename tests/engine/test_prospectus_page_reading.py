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


def price_lines(tables):
    return {(line["line"], line["per_unit"], line["total"])
            for name in ("cover_line", "turned_price", "turned_discount", "turned_proceeds") for line in tables.get(name, [])}


def test_the_price_lines_carry_their_amount_per_share_and_in_total():
    lines = {line["line"]: (line["per_unit"], line["total"]) for line in read()["cover_line"]}
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



NOTE = ("<html><body><p>Filed Pursuant to Rule 424(b)(2)</p><p>Invented Bank $250,000 Contingent Coupon Notes Linked to the"
        " Invented Index Fund</p>"
        "<table><tr><td></td><td>Price to Public(1)</td><td>Agent Discount(1)(2)</td><td>Proceeds to the Issuer</td></tr>"
        "<tr><td>Per Note</td><td>$1,000.00</td><td>$12.50</td><td>$987.50</td></tr>"
        "<tr><td>Total</td><td>$250,000.00</td><td>$3,125.00</td><td>$246,875.00</td></tr></table>"
        "<p>The Invented Index Fund is listed on the NYSE Arca under the symbol \u201cIIFX.\u201d</p>"
        "<p>The Invented Measure is reported by an invented vendor under the ticker symbol \u201cIMSR.\u201d</p>"
        "<p>The notes will not be listed on any securities exchange.</p></body></html>")


def test_a_note_whose_table_is_turned_gives_its_lines_per_note_and_in_total():
    assert price_lines(read(NOTE)) == {
        ("offering_price", "1000.00", None), ("offering_price", None, "250000.00"),
        ("underwriting_discount", "12.50", None), ("underwriting_discount", None, "3125.00"),
        ("proceeds", "987.50", None), ("proceeds", None, "246875.00")}


def test_a_linked_funds_symbol_and_exchange_are_not_the_offerings():
    (offering,) = read(NOTE)["offering"]
    assert (offering["ticker"], offering["exchange"], offering["shares_offered"]) == (None, None, None)


def test_the_issuers_own_listing_is_read_however_it_is_worded():
    page = ("<html><body><p>Our common stock has been approved for listing on the Nasdaq Capital Market under the ticker symbol"
            " \u201cINVQ.\u201d</p></body></html>")
    (offering,) = read(page)["offering"]
    assert (offering["ticker"], offering["exchange"]) == ("INVQ", "Nasdaq Capital Market")


def test_a_label_with_footnote_marks_and_a_dollar_sign_cell_is_read():
    page = ("<html><body><table><tr><td></td><td>Per Share</td><td>Total</td></tr>"
            "<tr><td>Public offering price(1)(2)</td><td>$</td><td>25.00</td><td>$</td><td>20,000,000</td></tr>"
            "<tr><td>Proceeds to us, before expenses</td><td>$</td><td>24.21</td><td>$</td><td>19,368,000</td></tr>"
            "<tr><td>Price to Public</td><td>$</td><td>$</td></tr></table></body></html>")
    assert price_lines(read(page)) == {("offering_price", "25.00", "20000000"), ("proceeds", "24.21", "19368000")}
