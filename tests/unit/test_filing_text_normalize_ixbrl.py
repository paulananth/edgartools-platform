"""release-readiness Ticket 101: modern (iXBRL-mandated since ~2019) EDGAR
filings embed non-rendered XBRL machinery (<ix:header>, display:none-styled
elements) that BeautifulSoup.get_text() has no CSS/XBRL awareness to skip,
contaminating extracted text with taxonomy noise instead of business-
description prose. Confirmed live against 21 real SEC filings spanning
1997-2026 (see the ticket's Answer section) -- all 5 modern iXBRL filings
affected, all 16 pre-iXBRL filings unaffected.

Fixtures below use REAL fragments captured verbatim from a real filing
(accession 0001609151-26-000016, weav-20251231.htm) -- a hand-written
"looks like iXBRL" fixture risks not matching SEC's actual convention
(here: <ix:header> is itself nested inside a display:none div, a detail
that would be easy to get wrong by construction) -- per this file's own
CLAUDE.md lesson on real-schema fixtures over hand-rolled stubs.
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
        """Provably a no-op on legacy filings: none of these elements exist in
        them (confirmed live against the pre-iXBRL half of the 21-filing
        sample), so the fix must not alter their extraction at all."""
        html = "<html><body><p>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</p></body></html>"

        text = _normalize_text(payload=html.encode("utf-8"), source_document_name="legacy10k.htm")

        assert "UNITED STATES SECURITIES AND EXCHANGE COMMISSION" in text
