"""release-readiness Ticket 101: modern (iXBRL-mandated since ~2019) EDGAR
filings embed non-rendered XBRL machinery (<ix:header>, display:none-styled
elements) that BeautifulSoup.get_text() has no CSS/XBRL awareness to skip,
contaminating extracted text with taxonomy noise instead of business-
description prose. Confirmed live against 21 real SEC filings spanning
1997-2026 (see the ticket's Answer section) -- all 5 modern iXBRL filings
affected, all 16 pre-iXBRL filings unaffected.

The two cases this fix must pin -- iXBRL contamination removed, and a
legacy pre-iXBRL filing left alone -- both use fragments captured
verbatim from real filings rather than hand-rolled HTML, per this
repo's own CLAUDE.md lesson on real-schema fixtures over hand-rolled
stubs: a "looks like iXBRL"/"looks like legacy HTML" fixture risks not
matching SEC's actual convention by construction (here: <ix:header> is
itself nested inside a display:none div in the real filing, and the
real legacy filing turns out to use "DISPLAY: inline/block" everywhere
-- both details easy to get wrong, or to accidentally not exercise at
all, if hand-written). The modern-filing fragments are from accession
0001609151-26-000016 (weav-20251231.htm); the legacy fragment is from
accession 0001144204-11-054283 (v235465_10k.htm, filed 2011). The two
extra defensive-regex tests (case/whitespace variant, false-positive
substring guard) use synthetic style strings deliberately -- they test
regex robustness in the abstract, not SEC's document conventions, so a
real-filing fixture buys nothing extra there.
"""
from __future__ import annotations

from edgar_warehouse.filing_text_projection import _normalize_text

# Trimmed to 3 of the real filing's ~30 <ix:nonnumeric> facts (enough to
# prove stripping works; the full block is ~82KB, irrelevant to this test).
# Verbatim from the real filing except for this trim.
_REAL_IX_HEADER_IN_DISPLAY_NONE_DIV = (
    '<div style="display:none">'
    "<ix:header><ix:hidden>"
    '<ix:nonnumeric contextref="c-1" id="f-32" name="dei:EntityCentralIndexKey">0001609151</ix:nonnumeric>'
    '<ix:nonnumeric contextref="c-1" format="ixt:fixed-false" id="f-33" name="dei:AmendmentFlag">false</ix:nonnumeric>'
    '<ix:nonnumeric contextref="c-1" id="f-34" name="dei:DocumentFiscalYearFocus">2025</ix:nonnumeric>'
    "</ix:hidden></ix:header>"
    "</div>"
)

# Verbatim real visible-prose paragraph from the same filing.
_REAL_VISIBLE_PARAGRAPH = (
    '<div style="margin-bottom:12pt">'
    '<span style="color:#000000;font-family:\'Arial\',sans-serif;font-size:10pt;font-weight:400;line-height:120%">'
    "Part III incorporates by reference certain information from the registrant’s definitive proxy statement, "
    "or the 2026 Proxy Statement, relating to its 2026 Annual Meeting of Stockholders. The 2026 Proxy Statement "
    "will be filed with the United States Securities and Exchange Commission within 120 days after the end of "
    "the fiscal year to which this report relates."
    "</span></div>"
)


def _wrap(*fragments: str) -> str:
    return "<html><body>" + "".join(fragments) + "</body></html>"


# Verbatim real fragment from a pre-iXBRL 10-K (accession 0001144204-11-054283,
# v235465_10k.htm, filed 2011) -- deliberately used for the no-op regression
# below instead of hand-rolled HTML: it's a real document that heavily uses
# the "DISPLAY:" style property (inline/block, uppercase, no colon-spacing)
# on nearly every element, which is exactly the shape the false-positive
# guard (test_a_style_that_merely_contains_the_substring_display_none_is_not_stripped
# above) needs to survive against real-world data, not just a synthetic case.
_REAL_PRE_IXBRL_FRAGMENT = (
    '<body bgcolor="#ffffff" style="DISPLAY: inline; FONT-SIZE: 10pt; FONT-FAMILY: Times New Roman">\n'
    '<div style="DISPLAY: block; TEXT-INDENT: 0pt"><br/>\n'
    "</div>\n"
    '<div align="center" style="DISPLAY: block; MARGIN-LEFT: 0pt; TEXT-INDENT: 0pt; MARGIN-RIGHT: 0pt">'
    '<font style="DISPLAY: inline; FONT-WEIGHT: bold; FONT-SIZE: 10pt; FONT-FAMILY: Times New Roman">'
    "U.S. SECURITIES AND EXCHANGE COMMISSION</font></div>\n"
    '<div align="center" style="DISPLAY: block; MARGIN-LEFT: 0pt; TEXT-INDENT: 0pt; MARGIN-RIGHT: 0pt">'
    '<font style="DISPLAY: inline; FONT-SIZE: 10pt; FONT-FAMILY: Times New Roman">'
    "Washington, D.C. 20549</font></div>\n"
    '<div style="DISPLAY: block; TEXT-INDENT: 0pt">\n'
    "<div> </div>\n"
    "<div>\n"
    '<hr align="center" noshade="" size="1" style="COLOR: black" width="12%"/>\n'
    "</div>\n"
    "<div> </div>\n"
    "</div>\n"
    '<div align="center" style="DISPLAY: block; MARGIN-LEFT: 0pt; TEXT-INDENT: 0pt; MARGIN-RIGHT: 0pt">'
    '<font style="DISPLAY: inline; FONT-SIZE: 10pt; FONT-FAMILY: Times New Roman">FORM 10-K</font></div>'
)


class TestNormalizeTextStripsHiddenIxbrlContent:
    def test_ix_header_and_display_none_content_excluded_from_modern_filing(self) -> None:
        html = _wrap(_REAL_IX_HEADER_IN_DISPLAY_NONE_DIV, _REAL_VISIBLE_PARAGRAPH)

        text = _normalize_text(payload=html.encode("utf-8"), source_document_name="weav-20251231.htm")

        assert "0001609151" not in text
        assert "dei:EntityCentralIndexKey" not in text
        assert "Part III incorporates by reference" in text

    def test_case_and_whitespace_variants_of_display_none_are_stripped(self) -> None:
        html = _wrap(
            '<div style="DISPLAY: NONE">hidden-variant-marker</div>',
            _REAL_VISIBLE_PARAGRAPH,
        )

        text = _normalize_text(payload=html.encode("utf-8"), source_document_name="test.htm")

        assert "hidden-variant-marker" not in text
        assert "Part III incorporates by reference" in text

    def test_a_style_that_merely_contains_the_substring_display_none_is_not_stripped(self) -> None:
        """Regression guard for the substring-matching risk /gof-refactor-reviewer
        flagged before this fix was implemented: a real display property whose
        value is NOT none must survive, even if "none" appears elsewhere in the
        same style string."""
        html = _wrap(
            '<div style="border-style:none;display:block">visible-marker</div>',
            _REAL_VISIBLE_PARAGRAPH,
        )

        text = _normalize_text(payload=html.encode("utf-8"), source_document_name="test.htm")

        assert "visible-marker" in text

    def test_pre_ixbrl_filing_with_no_hidden_elements_is_unaffected(self) -> None:
        """Provably a no-op on legacy filings: none of the elements this fix
        strips exist in them (confirmed live against the pre-iXBRL half of
        the 21-filing sample), so the fix must not alter their extraction at
        all -- proven here against a real captured pre-iXBRL fragment, not a
        hand-rolled stand-in, since the fragment's own heavy real-world use
        of "DISPLAY: inline"/"DISPLAY: block" (never "none") is exactly what
        would expose a false-positive in the strip logic if one existed."""
        html = "<html>" + _REAL_PRE_IXBRL_FRAGMENT + "</html>"

        text = _normalize_text(payload=html.encode("utf-8"), source_document_name="v235465_10k.htm")

        assert "U.S. SECURITIES AND EXCHANGE COMMISSION" in text
        assert "Washington, D.C. 20549" in text
        assert "FORM 10-K" in text
