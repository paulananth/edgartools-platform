from __future__ import annotations

from datetime import date

from edgar_warehouse.application.subsidiary_exhibits import parse_subsidiary_exhibit


def test_exhibit_21_rows_preserve_name_jurisdiction_and_reported_parent_scope() -> None:
    result = parse_subsidiary_exhibit(
        accession_number="0001-26-000001",
        registrant_cik=1001,
        document_name="ex21.htm",
        document_type="EX-21.1",
        content="""
        <html><table>
          <tr><th>Subsidiary</th><th>Jurisdiction</th></tr>
          <tr><td>Alpha Holdings LLC</td><td>Delaware</td></tr>
          <tr><td>Beta Limited</td><td>England and Wales</td></tr>
        </table></html>
        """,
        report_date=date(2025, 12, 31),
        source_sha256="sha-ex21",
    )

    assert result.outcome == "applicable_loaded"
    assert [(row.legal_name, row.jurisdiction) for row in result.rows] == [
        ("Alpha Holdings LLC", "Delaware"),
        ("Beta Limited", "England and Wales"),
    ]
    assert all(row.parent_scope == "registrant_disclosed" for row in result.rows)
    assert all(row.immediate_parent_known is False for row in result.rows)


def test_exhibit_explicit_no_disclosable_subsidiaries_is_terminal_zero() -> None:
    result = parse_subsidiary_exhibit(
        accession_number="0001-26-000002",
        registrant_cik=1001,
        document_name="ex21.txt",
        document_type="EX-21",
        content="The registrant has no subsidiaries required to be listed under Item 601(b)(21).",
        report_date=date(2025, 12, 31),
        source_sha256="sha-zero",
    )

    assert result.outcome == "not_applicable"
    assert result.reason == "explicit_no_disclosable_subsidiaries_601_b21_ii"
    assert result.rows == ()
