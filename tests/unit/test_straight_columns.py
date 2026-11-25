"""Ticket 18: silver holds straight columns. The builds' JSON traces are the query's own form, never stored;
each becomes columns or a child table's rows. Every name and number here is invented."""

from decimal import Decimal

import pytest

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.financials import line_items, measures
from edgar_warehouse.mastering import links


def figure(flags, inputs=None, **more):
    return {"company_key": "0000000001", "line_item": "book_value", "fiscal_year": 2025, "flags": flags,
            "inputs": inputs, "value": Decimal(90)} | more


def test_flag_words_become_columns_and_inputs_become_rows():
    rows = [figure(["computed", "includes NCI", "revenue quality check"], [
        {"concept": "Equity", "accession_number": "0000000001-26-000001", "filed": "2026-02-01", "value": "100.0000000000"},
        {"line_item": "revenue", "value": "5.5", "term": 3}])]
    tables = line_items.straight(rows)
    (parent,) = tables["company_line_item"]
    assert "flags" not in parent and "inputs" not in parent
    assert (parent["computed"], parent["basis"], parent["industry_kind"], parent["revenue_quality_check"]) == (
        True, "includes NCI", None, True)
    first, second = tables["company_line_item_input"]
    assert (first["position"], first["concept"], first["line_item_ref"], first["value"], first["filed"]) == (
        1, "Equity", None, "100.0000000000", "2026-02-01")  # no term number: the cover-page count is the first
    assert (second["position"], second["concept"], second["line_item_ref"], second["accession_number"]) == (
        3, None, "revenue", None)  # the map's third term: an optional second one had no figure


def test_an_industry_kind_is_its_own_column_and_a_plain_figure_has_none_of_them():
    kind, plain = line_items.straight([figure(["kind: bank"]), figure([])])["company_line_item"]
    assert (kind["industry_kind"], kind["basis"], kind["computed"]) == ("bank", None, False)
    assert (plain["industry_kind"], plain["basis"], plain["computed"], plain["revenue_quality_check"]) == (
        None, None, False, False)


def test_two_basis_wordings_on_one_figure_are_refused():
    with pytest.raises(Blocked, match="more than one basis wording"):
        line_items.straight([figure(["includes NCI", "cash only"])])


def test_a_measure_input_is_a_row_for_its_figure_and_one_for_each_part_and_the_tax_rate():
    row = {"company_key": "0000000001", "measure": "roic_beginning", "fiscal_year": 2025, "window_years": 1,
           "value": Decimal("0.6"), "inputs": {
               "return": {"fiscal_year": 2025, "value": "75.0", "concept": "computed",
                          "operating_income": {"value": "100.0", "concept": "OperatingIncomeLoss",
                                               "accession_number": "0000000001-26-000001"},
                          "tax_rate": "0.25", "rate_source": "statutory: US"},
               "balance": {"fiscal_year": 2024}}}
    tables = measures.straight([row])
    assert "inputs" not in tables["company_measure"][0]
    got = {(r["role"], r["part"]): r for r in tables["company_measure_input"]}
    assert set(got) == {("return", "figure"), ("return", "operating_income"), ("return", "tax_rate")}
    assert (got[("return", "tax_rate")]["value"], got[("return", "tax_rate")]["basis"]) == ("0.25", "statutory: US")
    assert got[("return", "operating_income")]["accession_number"] == "0000000001-26-000001"
    assert {r["input_fiscal_year"] for r in got.values()} == {2025}  # an input with no figure has no row


def edge(**more):
    return {"relationship_id": "r1", "type": "PARENT", "scope": "s", "source_id": "a", "target_id": "b",
            "evidence": [{"assertion_id": "y"}, {"assertion_id": "x"}], "periods": [
                {"valid_from": "2026-01-01T00:00:00+00:00", "valid_from_basis": "stated", "path": ["p", "q"],
                 "properties": {"source_event_type": "merger", "source_start_date_is_provisional": True}},
                {"valid_from": "2026-06-01T00:00:00+00:00", "valid_from_basis": "observed"}]} | more


def test_links_become_periods_with_property_columns_one_evidence_row_a_link_and_path_steps():
    tables = links.rows_of([edge()])
    first, second = tables["relationship"]
    assert "path" not in first and "evidence" not in first and "properties" not in first
    assert (first["source_event_type"], first["source_start_date_is_provisional"], first["source_entity_status"]) == (
        "merger", True, None)
    assert second["source_event_type"] is None
    assert [e["assertion_id"] for e in tables["relationship_evidence"]] == ["x", "y"]  # once, not once a period
    assert [(s["position"], s["step_relationship_id"], s["valid_from"]) for s in tables["relationship_path"]] == [
        (1, "p", "2026-01-01T00:00:00+00:00"), (2, "q", "2026-01-01T00:00:00+00:00")]


def test_a_property_no_silver_column_holds_is_refused():
    bad = edge(periods=[{"valid_from": "t", "valid_from_basis": "stated", "properties": {"invented": "x"}}])
    with pytest.raises(ValueError, match="no silver column holds"):
        links.rows_of([bad])


def test_a_stored_period_gives_back_the_properties_it_was_calculated_with():
    """The engine keeps a start only when the stored period equals the new one: a declared property that was
    empty comes back as null, and a flag comes back as a flag."""
    declared = {"source_event_type": "merger", "source_event_status": None, "source_start_date_is_provisional": True}
    tables = links.rows_of([edge(periods=[
        {"valid_from": "2026-01-01T00:00:00+00:00", "valid_from_basis": "observed", "properties": declared},
        {"valid_from": "2026-06-01T00:00:00+00:00", "valid_from_basis": "observed",
         "properties": declared | {"source_event_status": "done"}}])])
    rows, declares = [{**row, "valid_to": None, "valid_to_basis": None} for row in tables["relationship"]], {}
    for row in rows:
        links._declare(declares, row)
    stored = links.stored_of(rows, declares)
    first, second = stored["r1"]["periods"]
    assert first["properties"] == declared | {"source_event_status": None} | {}
    assert second["properties"] == declared | {"source_event_status": "done"}
    assert "source_entity_status" not in first["properties"]
