from __future__ import annotations

from datetime import date

import pytest

from edgar_warehouse.application.effective_thirteenf import (
    ThirteenFFiling,
    effective_filing_set,
)


def test_restatement_supersedes_base_and_addition_supplements() -> None:
    filings = [
        ThirteenFFiling("base", 1, date(2024, 3, 31), date(2024, 5, 1), "13F-HR"),
        ThirteenFFiling("restated", 1, date(2024, 3, 31), date(2024, 5, 4),
                        "13F-HR/A", amendment_type="restatement"),
        ThirteenFFiling("added", 1, date(2024, 3, 31), date(2024, 5, 5),
                        "13F-HR/A", amendment_type="added_holdings"),
    ]
    result = effective_filing_set(filings)
    assert [row.accession_number for row in result.effective] == ["restated", "added"]
    assert result.superseded == {"base": "restated"}


def test_amendment_without_semantics_fails_closed() -> None:
    with pytest.raises(ValueError, match="amendment_type"):
        effective_filing_set([
            ThirteenFFiling("a", 1, date(2024, 3, 31), date(2024, 5, 1), "13F-HR/A")
        ])
