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
    _strip_name_markers,
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


class TestTicket26Residues:
    """The three residues ticket 10's full bronze re-parse left behind.

    Every ``raw`` below is a real ``exec_name`` value from that re-parse
    (``research/10-reparse-results.json``), so these pin the exact layouts
    that survived the first repair, not invented ones.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # 462 rows kept a marker: the name alone, marker glued or spaced.
            ("Jeff Zhu(1)", "Jeff Zhu"),
            ("Aman Narang (4)", "Aman Narang"),
            ("Travis D. Stice(7)", "Travis D. Stice"),
            ("JOHN J. CHADWICK(5)", "JOHN J. CHADWICK"),
            ("Kodwo Ghartey-Tagoe(1)", "Kodwo Ghartey-Tagoe"),
            ("R. Bryan Riggsbee (⁸)", "R. Bryan Riggsbee"),
            ("R. Bryan Riggsbee⁸", "R. Bryan Riggsbee"),
            # A marker sitting between the name and its title.
            ("Jason Dies(1)Interim", "Jason Dies"),
            ("Stephanie Williams (10)VP and", "Stephanie Williams"),
            ("Jeffrey H. Duncan (5) V.P., Manufacturing & Engineering", "Jeffrey H. Duncan"),
        ],
    )
    def test_footnote_markers_are_stripped_wherever_they_sit(self, raw, expected):
        assert _names([FakeEntry(raw, "", 2023)])[0][0] == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # 128 rows kept the first half of "Co-CEO" or "- Chief ...".
            ("Chi-Foon Chan Co-", "Chi-Foon Chan"),
            ("TED SARANDOS co-", "TED SARANDOS"),
            ("Aart J. de Geus Co-", "Aart J. de Geus"),
            ("Aart J. de GeusCo-", "Aart J. de Geus"),
            ("Lori Bisson -", "Lori Bisson"),
            ("Emiliano Kargieman -", "Emiliano Kargieman"),
            # The same separator, this time with the position behind it.
            ("Walter Klemp - Executive Chair (8)", "Walter Klemp"),
            ("Mitchell B. Goldsteen - Executive Chairman", "Mitchell B. Goldsteen"),
            ("Ariel Porat - Former", "Ariel Porat"),
        ],
    )
    def test_trailing_title_fragments_start_the_title(self, raw, expected):
        assert _names([FakeEntry(raw, "", 2023)])[0][0] == expected

    def test_a_cut_fragment_becomes_title_text(self):
        """The fragment is the start of the position, so it joins the title."""
        repaired = _repair_entry_names(
            [FakeEntry("Chi-Foon Chan Co-", "", 2023), FakeEntry("Chief Executive Officer", "", 2022)]
        )
        assert [e.name for e in repaired] == ["Chi-Foon Chan"] * 2
        assert repaired[0].title == "Co- Chief Executive Officer"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # 167 rows kept role text research 01's check already rejects.
            ("Max P. Bowman, VP/", "Max P. Bowman"),
            ("Charles J. Hardin, VP/Sales", "Charles J. Hardin"),
            ("Jack B. Self, VP/Operations", "Jack B. Self"),
            ("Gordon D. Wichman VP", "Gordon D. Wichman"),
            ("John F. Quanci VP", "John F. Quanci"),
            ("Geoffrey Davies VP &", "Geoffrey Davies"),
            ("Geoffrey DaviesVP &", "Geoffrey Davies"),
            ("Richard J. WehrleVP &", "Richard J. Wehrle"),
            ("Jane Q. Doe SEVP and", "Jane Q. Doe"),
            ("Jeffrey H. Duncan V.P.-Manufacturing & Engineering", "Jeffrey H. Duncan"),
            ("Jeffrey H. Duncan V.P. - Manufacturing & Engineering", "Jeffrey H. Duncan"),
        ],
    )
    def test_vp_spellings_open_a_title(self, raw, expected):
        assert _names([FakeEntry(raw, "", 2023)])[0][0] == expected

    @pytest.mark.parametrize("cell", ["VP/Sales", "1st VP/", "Jr., VP/", "SEVP and", "VP of Processing"])
    def test_vp_only_cells_are_never_names(self, cell):
        entries = [FakeEntry("Ana P. Reyes", "Chief Executive Officer", 2023), FakeEntry(cell, "", 2022)]
        assert [n for n, _, _ in _names(entries)] == ["Ana P. Reyes"] * 2

    @pytest.mark.parametrize(
        "name",
        [
            "Chi-Foon Chan",
            "Jean-Luc Picard",
            "Mary-Kate Olsen",
            "Vipul Shah",
            "Sevpal Singh",
            "Coco Deveaux",
            "Marco Vitti",
        ],
    )
    def test_names_the_new_rules_must_not_cut(self, name):
        """Hyphenated given names, and surnames that merely contain the new
        vocabulary, survive the trailing-fragment and VP rules intact."""
        assert _names([FakeEntry(name, "Chief Executive Officer", 2023)])[0][0] == name

    @pytest.mark.parametrize("name", ["Robert (Bob) Smith", "Robert (B) Smith"])
    def test_a_parenthesised_nickname_or_initial_is_not_a_footnote_marker(self, name):
        """Only digits and single *lowercase* letters mark footnotes, so a
        bracketed capital initial survives ("Justin Cochrane(f)" is a marker)."""
        assert _names([FakeEntry(name, "", 2023)])[0][0] == name

    def test_a_lowercase_letter_marker_is_stripped(self):
        assert _names([FakeEntry("Justin Cochrane(f)", "", 2023)])[0][0] == "Justin Cochrane"

    @pytest.mark.parametrize("name", ["Anthony Franco-", "Joseph Marco-"])
    def test_a_surname_ending_in_co_is_not_cut(self, name):
        """Regression: a lowercase glued "co-" would cut "Franco" to "Fran",
        the same hazard ``_CAMEL_TITLE_RE``'s case sensitivity exists to avoid."""
        assert _names([FakeEntry(name, "", 2023)])[0][0] == name.rstrip("-")

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # A superscript the HTML flattened to a plain digit: 56 rows of the
            # ticket 26 re-parse. It gave one executive a different spelling in
            # each year's filing ("Daniel Pinto7" / "Pinto8" / "Pinto11").
            ("Brendan Brothers6", "Brendan Brothers"),
            ("Marianne Lake11", "Marianne Lake"),
            ("Charles R. Schwab5", "Charles R. Schwab"),
            ("Walter W. Bettinger II6", "Walter W. Bettinger II"),
            ("Terry D. Peterson 5", "Terry D. Peterson"),
        ],
    )
    def test_a_flattened_superscript_digit_is_stripped(self, raw, expected):
        assert _names([FakeEntry(raw, "", 2023)])[0][0] == expected

    def test_digits_inside_a_position_are_not_markers(self):
        """Only a digit glued to a word, or a lone trailing one, is a marker."""
        repaired = _repair_entry_names([FakeEntry("Ana P. Reyes", "Chief Executive Officer", 2023)])
        assert repaired[0].name == "Ana P. Reyes"
        assert _strip_name_markers("Section 16 Officer") == "Section 16 Officer"
        assert _strip_name_markers("1st VP/") == "1st VP/"

    def test_a_marker_list_is_stripped(self):
        assert _names([FakeEntry("Robert M. Robuck (6, 7)", "", 2023)])[0][0] == "Robert M. Robuck"

    def test_all_three_residues_in_one_cell(self):
        """Real cell: a glued marker in front of the new vocabulary."""
        assert _names([FakeEntry("Malcolm G. Cooke(3)V.P.", "", 2023)])[0][0] == "Malcolm G. Cooke"

    @pytest.mark.parametrize("name", ["John SmithVIP", "Ana SilvaVIP", "Raj DeviVAP"])
    def test_the_v_p_entry_is_not_a_wildcard(self, name):
        """Regression: "v.p" is the first vocabulary entry carrying a regex
        metacharacter. Unescaped, its dot matches any letter, so "SmithVIP"
        would split into a name and a title that no proxy ever wrote."""
        assert _names([FakeEntry(name, "Chief Executive Officer", 2023)])[0][0] == name

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
