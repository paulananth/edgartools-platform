"""Tests for the edgartools-based 13F filer list builder."""

from __future__ import annotations

import pandas as pd
import pytest

from edgar_warehouse.scripts.build_13f_filer_list import collect_13f_ciks


class _FakeFilings:
    def __init__(self, ciks: list[int]) -> None:
        self._ciks = ciks

    def to_pandas(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "cik": self._ciks,
                "form": ["13F-HR"] * len(self._ciks),
            }
        )


def test_collect_13f_ciks_dedupes_across_quarters_and_years() -> None:
    # 2020 Q1-Q4, 2021 Q1-Q4 = 8 calls. CIK 100 recurs every quarter (as a real
    # institutional manager would, since 13F-HR is filed quarterly); CIK 200
    # only appears in 2020 Q2; CIK 300 only appears in 2021 Q4.
    responses = {
        (2020, 1): [100],
        (2020, 2): [100, 200],
        (2020, 3): [100],
        (2020, 4): [100],
        (2021, 1): [100],
        (2021, 2): [100],
        (2021, 3): [100],
        (2021, 4): [100, 300],
    }
    calls: list[tuple[int, int, str]] = []

    def fake_get_filings(*, year: int, quarter: int, form: str):
        calls.append((year, quarter, form))
        return _FakeFilings(responses[(year, quarter)])

    result = collect_13f_ciks(2020, 2021, get_filings=fake_get_filings)

    assert result == [100, 200, 300]
    assert len(calls) == 8
    assert all(form == "13F-HR" for _, _, form in calls)
    assert (2020, 1, "13F-HR") in calls
    assert (2021, 4, "13F-HR") in calls


def test_collect_13f_ciks_skips_quarter_on_fetch_failure() -> None:
    def fake_get_filings(*, year: int, quarter: int, form: str):
        if (year, quarter) == (2020, 2):
            raise RuntimeError("simulated SEC fetch failure")
        return _FakeFilings([100])

    result = collect_13f_ciks(2020, 2020, get_filings=fake_get_filings)

    # 2020 Q1, Q3, Q4 succeed (CIK 100); Q2 fails and is skipped, not raised.
    assert result == [100]


def test_collect_13f_ciks_release_mode_fails_on_fetch_failure() -> None:
    def fake_get_filings(*, year: int, quarter: int, form: str):
        if quarter == 2:
            raise RuntimeError("simulated SEC fetch failure")
        return _FakeFilings([100])

    with pytest.raises(RuntimeError, match="2020 Q2"):
        collect_13f_ciks(2020, 2020, get_filings=fake_get_filings, strict=True)


def test_collect_13f_ciks_handles_empty_quarter() -> None:
    def fake_get_filings(*, year: int, quarter: int, form: str):
        if (year, quarter) == (2020, 3):
            return _FakeFilings([])
        return _FakeFilings([100])

    result = collect_13f_ciks(2020, 2020, get_filings=fake_get_filings)

    assert result == [100]


def test_collect_13f_ciks_defaults_to_edgartools_get_filings() -> None:
    import inspect

    import edgar

    sig = inspect.signature(collect_13f_ciks)
    assert sig.parameters["get_filings"].default is edgar.get_filings
