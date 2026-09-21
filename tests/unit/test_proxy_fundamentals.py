"""Unit tests for the DEF 14A proxy fundamentals parser.

Characterization plus the name-repair contract from Person Consumer Contract
ticket 10. The defect these pin down: edgartools' ``extract_summary_compensation``
walks the Summary Compensation Table row by row and overwrites the executive's
name with whatever sits in the name column, so the wrapped continuation lines of
a multi-line title ("Chairman of the" / "Board and Chief" / "Executive Officer")
become ``entry.name`` for every later year row in that executive's block. The
platform copied ``entry.name`` verbatim, which is why 47-59% of
``sec_executive_record.exec_name`` values are role text rather than people.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from edgar_warehouse.parsers.proxy_fundamentals import (
    _repair_entry_names,
    parse_proxy_fundamentals,
)


@dataclass(frozen=True)
class FakeEntry:
    """Stand-in for edgartools' ``ExecutiveCompEntry`` (frozen dataclass)."""

    name: str
    title: str = ""
    year: int = 2023
    salary: int | None = None
    bonus: int | None = None
    stock_awards: int | None = None
    option_awards: int | None = None
    non_equity_incentive: int | None = None
    total: int | None = None


def _names(entries):
    return [(e.name, e.title, e.year) for e in _repair_entry_names(entries)]


class TestNameRepair:
    def test_title_row_does_not_become_a_name(self):
        """The reported defect: row 2 of a block is the wrapped title."""
        entries = [
            FakeEntry("Tim Cook", "Chief Executive Officer", 2023),
            FakeEntry("Chief Executive Officer", "", 2022),
            FakeEntry("Chief Executive Officer", "", 2021),
        ]
        assert _names(entries) == [
            ("Tim Cook", "Chief Executive Officer", 2023),
            ("Tim Cook", "Chief Executive Officer", 2022),
            ("Tim Cook", "Chief Executive Officer", 2021),
        ]

    def test_multi_line_title_reassembles(self):
        """Three wrap fragments rebuild one title and never shadow the name."""
        entries = [
            FakeEntry("Jane A. Doe", "Chairman of the", 2023),
            FakeEntry("Board and Chief", "", 2022),
            FakeEntry("Executive Officer", "", 2021),
        ]
        repaired = _repair_entry_names(entries)
        assert [e.name for e in repaired] == ["Jane A. Doe"] * 3
        assert repaired[0].title == "Chairman of the Board and Chief Executive Officer"
        assert [e.year for e in repaired] == [2023, 2022, 2021]

    def test_footnote_marker_is_stripped(self):
        entries = [FakeEntry("Brian B. Yoor,(1)", "Chief Financial Officer", 2023)]
        assert _names(entries)[0][0] == "Brian B. Yoor"

    @pytest.mark.parametrize(
        "raw",
        ["Robert Smith*", "Robert Smith (2)", "Robert Smith†", "Robert Smith, (3)"],
    )
    def test_other_reference_markers_are_stripped(self, raw):
        assert _names([FakeEntry(raw)])[0][0] == "Robert Smith"

    def test_former_prefix_line_is_not_a_name(self):
        entries = [
            FakeEntry("Alice R. Brown", "Chief Financial Officer", 2023),
            FakeEntry("Former Chief Financial Officer", "", 2022),
        ]
        assert [n for n, _, _ in _names(entries)] == ["Alice R. Brown"] * 2

    def test_fragment_before_any_name_is_dropped(self):
        """Compensation that cannot be attributed to a person is not emitted."""
        entries = [
            FakeEntry("Chief Executive Officer", "", 2023, total=1_000),
            FakeEntry("Tim Cook", "Chief Executive Officer", 2022, total=2_000),
        ]
        repaired = _repair_entry_names(entries)
        assert [(e.name, e.year) for e in repaired] == [("Tim Cook", 2022)]

    def test_next_executive_resets_the_carry_forward(self):
        entries = [
            FakeEntry("Tim Cook", "Chief Executive Officer", 2023),
            FakeEntry("Chief Executive Officer", "", 2022),
            FakeEntry("Luca Maestri", "Chief Financial Officer", 2023),
            FakeEntry("Chief Financial Officer", "", 2022),
        ]
        assert [n for n, _, _ in _names(entries)] == [
            "Tim Cook",
            "Tim Cook",
            "Luca Maestri",
            "Luca Maestri",
        ]

    def test_single_token_cell_is_not_a_name(self):
        entries = [
            FakeEntry("Maria L. Santos", "President", 2023),
            FakeEntry("President", "", 2022),
        ]
        assert [n for n, _, _ in _names(entries)] == ["Maria L. Santos"] * 2

    def test_plain_table_is_unchanged(self):
        """Characterization: a well-formed table passes through untouched."""
        entries = [
            FakeEntry("Tim Cook", "Chief Executive Officer", 2023, total=63_000_000),
            FakeEntry("Luca Maestri", "Chief Financial Officer", 2023, total=27_000_000),
        ]
        assert _names(entries) == [
            ("Tim Cook", "Chief Executive Officer", 2023),
            ("Luca Maestri", "Chief Financial Officer", 2023),
        ]

    def test_compensation_values_survive_repair(self):
        entries = [
            FakeEntry("Tim Cook", "Chief Executive Officer", 2023, salary=3_000, total=63_000),
            FakeEntry("Chief Executive Officer", "", 2022, salary=3_000, total=99_000),
        ]
        repaired = _repair_entry_names(entries)
        assert [e.total for e in repaired] == [63_000, 99_000]
        assert [e.salary for e in repaired] == [3_000, 3_000]

    def test_name_and_title_share_one_cell(self):
        """The layout real proxies actually use (Apple 2024 DEF 14A).

        edgartools returns name and position run together in the name column;
        the name ends where the position begins.
        """
        entries = [
            FakeEntry("Tim Cook", "CEO", 2023),
            FakeEntry("Luca Maestri Senior Vice President", "CFO", 2023),
            FakeEntry("Deirdre O\u2019Brien Senior Vice", "President, Retail", 2023),
        ]
        repaired = _repair_entry_names(entries)
        assert [e.name for e in repaired] == [
            "Tim Cook",
            "Luca Maestri",
            "Deirdre O\u2019Brien",
        ]
        assert repaired[1].title == "Senior Vice President CFO"
        assert repaired[2].title == "Senior Vice President, Retail"

    def test_a_surname_that_starts_a_title_defers_to_title_text(self):
        """Documented limitation, chosen deliberately.

        A cell whose second token already begins a position ("Andrew Chief
        Bearheart") is read as title text, because a name needs two tokens
        before the position starts. Inventing a person from title text is
        worse than losing a rare surname, so the rule errs this way.
        """
        entries = [
            FakeEntry("Maria L. Santos", "Chief Executive Officer", 2023),
            FakeEntry("Andrew Chief Bearheart", "", 2022),
        ]
        assert [n for n, _, _ in _names(entries)] == ["Maria L. Santos"] * 2

    def test_no_space_between_name_and_title(self):
        """A third real layout: no separator at all (sampled bronze proxies)."""
        entries = [
            FakeEntry("Andreas G. FrankExecutive Vice President", "", 2023),
            FakeEntry("Doug SchoonerChief Manufacturing Officer", "", 2023),
            FakeEntry("Martin RaffieldSVP Operations", "", 2023),
        ]
        assert [n for n, _, _ in _names(entries)] == [
            "Andreas G. Frank",
            "Doug Schooner",
            "Martin Raffield",
        ]

    @pytest.mark.parametrize(
        "name",
        [
            "Marco Franco",
            "Sarah Whitehead",
            "Rocco Greco",
            "Bianca Blanco",
            "Alan Chairwell",
        ],
    )
    def test_surnames_containing_title_letters_are_not_split(self, name):
        """Regression: a case-insensitive split cut "Franco" at "co" and
        "Whitehead" at "head", inventing people from halves of real names."""
        assert _names([FakeEntry(name, "Chief Executive Officer", 2023)])[0][0] == name

    def test_position_only_cells_are_never_names(self):
        """Sampled from real proxies: stray cells that are all position text."""
        for cell in (
            "Director of Wholesale Banking",
            "Marketing Services",
            "Co-Founder and",
            "Retail Banking Division Manager",
        ):
            entries = [FakeEntry("Ana P. Reyes", "Chief Executive Officer", 2023), FakeEntry(cell, "", 2022)]
            assert [n for n, _, _ in _names(entries)] == ["Ana P. Reyes"] * 2

    def test_empty_input(self):
        assert _repair_entry_names([]) == []


class TestParseProxyFundamentals:
    """End-to-end through the adapter, with edgartools' extractor monkeypatched."""

    def _patch(self, monkeypatch, entries):
        import edgar.proxy.html_extractor as extractor

        monkeypatch.setattr(extractor, "extract_summary_compensation", lambda tree: entries)

    def test_rows_carry_the_repaired_name_and_role(self, monkeypatch):
        self._patch(
            monkeypatch,
            [
                FakeEntry("Tim Cook", "Chief Executive Officer", 2023, total=63_000_000),
                FakeEntry("Chief Executive Officer", "", 2022, total=99_000_000),
            ],
        )
        out = parse_proxy_fundamentals(
            accession_number="0000320193-24-000045",
            content="<html><body><table><tr><td>x</td></tr></table></body></html>",
            form_type="DEF 14A",
            cik=320193,
        )
        rows = out["sec_executive_record"]
        assert [r["exec_name"] for r in rows] == ["Tim Cook", "Tim Cook"]
        assert [r["exec_role"] for r in rows] == ["CEO", "CEO"]
        assert [r["fiscal_year"] for r in rows] == [2023, 2022]
        assert [r["total_comp"] for r in rows] == [63_000_000.0, 99_000_000.0]
        assert {r["cik"] for r in rows} == {320193}

    def test_unattributable_rows_are_not_emitted(self, monkeypatch):
        self._patch(monkeypatch, [FakeEntry("Executive Officer", "", 2023, total=1)])
        out = parse_proxy_fundamentals(
            accession_number="0000320193-24-000045",
            content="<html><body><table><tr><td>x</td></tr></table></body></html>",
            form_type="DEF 14A",
            cik=320193,
        )
        assert out["sec_executive_record"] == []

    def test_a_non_dataclass_entry_degrades_to_no_records(self, monkeypatch):
        """The module's contract: a parser returns no records, never raises."""

        class NotADataclass:
            name = "Tim Cook"
            title = "Chief Executive Officer"
            year = 2023
            total = 1

        self._patch(monkeypatch, [NotADataclass()])
        out = parse_proxy_fundamentals(
            accession_number="0000320193-24-000045",
            content="<html><body><table><tr><td>x</td></tr></table></body></html>",
            form_type="DEF 14A",
            cik=320193,
        )
        assert out == {"sec_executive_record": []}

    def test_no_table_returns_empty(self, monkeypatch):
        self._patch(monkeypatch, None)
        out = parse_proxy_fundamentals(
            accession_number="0000320193-24-000045",
            content="<html><body></body></html>",
            form_type="DEF 14A",
            cik=320193,
        )
        assert out == {"sec_executive_record": []}
