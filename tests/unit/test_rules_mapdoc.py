"""Rules skill ticket 11: the Mapping Document, a spreadsheet held equal to the rules."""

from __future__ import annotations

import shutil

import pytest

from edgar_warehouse.rules import files, mapdoc


def test_every_committed_mapping_document_equals_its_rules():
    """A workbook that differs from the rules it is generated from fails here:
    a steward's change must become rules, or be regenerated away, before it
    merges. Fix with `edgar-warehouse rules mapdoc write`."""
    for path, (sheets, _) in mapdoc.documents().items():
        assert mapdoc.differences(path, sheets) == [], path


def test_only_sources_that_feed_mdm_have_one():
    names = {path.parent.name if path.name == "MAPPING.xlsx" else path.stem for path in mapdoc.documents()}
    assert names == {"gleif", "sec.submissions.company", "company"}


@pytest.fixture
def rules_copy(tmp_path):
    root = tmp_path / "rules"
    shutil.copytree(files.ROOT, root)
    return root


def _write_all(root):
    for path, (sheets, sources) in mapdoc.documents(root).items():
        mapdoc.write(path, sheets, sources)
    return mapdoc.documents(root)


def test_a_steward_change_is_reported_cell_by_cell(rules_copy):
    found = _write_all(rules_copy)
    path = rules_copy / "sources" / "gleif" / "MAPPING.xlsx"
    from openpyxl import load_workbook

    book = load_workbook(path)
    sheet = book["Critical data elements"]
    sheet.append(["gleif.level1.v1", "address", "Exception", ""])
    book["Who wins"]["C2"] = "1"
    book.save(path)
    lines = mapdoc.differences(path, found[path][0])
    assert any("Critical data elements row 3: added in the workbook" in line and "address" in line for line in lines)
    assert any("Who wins row 2" in line and 'rules say "2", workbook says "1"' in line for line in lines)


def test_notes_are_kept_when_the_workbook_is_regenerated(rules_copy):
    found = _write_all(rules_copy)
    path = rules_copy / "merge" / "kinds" / "company.xlsx"
    from openpyxl import load_workbook

    book = load_workbook(path)
    book[mapdoc.NOTES].append(["Rank SEC first for names", "Preferred sources", "a steward", "2026-09-28"])
    book.save(path)
    mapdoc.write(path, *found[path])
    notes = mapdoc.read(path)[mapdoc.NOTES]
    assert ["Rank SEC first for names", "Preferred sources", "a steward", "2026-09-28"] in notes
    assert mapdoc.differences(path, found[path][0]) == []


def test_a_new_workbook_keeps_the_decisions_the_rules_comments_hold(rules_copy):
    found = mapdoc.documents(rules_copy)
    path = rules_copy / "sources" / "sec.submissions.company" / "MAPPING.xlsx"
    path.unlink(missing_ok=True)
    mapdoc.write(path, *found[path])
    notes = mapdoc.read(path)[mapdoc.NOTES]
    assert notes[0] == mapdoc.NOTES_HEADER
    assert any(row[1] == "source.yaml: identifiers" and "EIN" in row[0] for row in notes)


def test_the_sheets_say_what_the_rules_say():
    found = mapdoc.documents()
    sec = found[files.ROOT / "sources" / "sec.submissions.company" / "MAPPING.xlsx"][0]
    assert ["sec.submissions.company.v1", "cik", "cik", "sec_cik", "Yes", "Only with a new dataset code",
            "mdm.sec.submissions.company.v1.contract.adapter.identifiers.cik"] in sec["Identifiers"]
    assert [row[1] for row in sec["Critical data elements"][1:]] == ["name"]
    assert ["company", "sec.submissions.company.v1", "1", "merge/kinds/company.yaml defaults.sources"] in sec["Who wins"]
    kind = found[files.ROOT / "merge" / "kinds" / "company.xlsx"][0]
    assert [row[1] for row in kind["Matching rules"][1:]] == ["sec-gleif-name-jurisdiction", "sec-gleif-name-postal"]
    assert len(kind["Classification"]) == 15  # the 14 steps of sec-company-candidate


def test_a_long_list_shows_as_a_count():
    assert mapdoc._text(list(range(13))) == "13 values (see the rules file)"
    assert mapdoc._text(["A", "B"]) == "A, B"
