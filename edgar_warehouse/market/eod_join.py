"""ERDP-07 market EOD join helpers (Explore-only).

Resolves CIK → ticker (from TICKER_REFERENCE-shaped rows), fetches EOD
close / market cap / beta via :class:`PriceProvider`, and derives enterprise
value using gold debt and cash.  These outputs are **not** pure-SEC Decision
Features (ADR 0001) and must not be injected into ``subject_features``.

See ``docs/er-market-eod-join.md``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

SOURCE_SYSTEM_YAHOO = "yahoo"

# Canonical Explore grade label for consumer docs / recipes.
EXPLORE_GRADE = "explore"


@dataclass(frozen=True)
class EodSnapshot:
    """Point-in-time market snapshot for one ticker (Explore)."""

    ticker: str
    as_of: str
    close: float | None
    market_cap: float | None
    beta: float | None
    source_system: str = SOURCE_SYSTEM_YAHOO
    grade: str = EXPLORE_GRADE
    cik: str | None = None
    currency: str = "USD"
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_cik(cik: str | int | None) -> str | None:
    """Return zero-padded 10-digit CIK string, or None if empty/invalid."""
    if cik is None:
        return None
    raw = str(cik).strip()
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    return digits.zfill(10)


def pick_primary_ticker(
    ticker_rows: Sequence[Mapping[str, Any]],
    cik: str | int,
    *,
    preferred_exchange: str | None = None,
) -> str | None:
    """Pick a primary trading ticker for *cik* from TICKER_REFERENCE-shaped rows.

    Rows are expected to have at least ``cik`` and ``ticker`` keys (optional
    ``exchange``).  Preference order:

    1. Match preferred exchange (case-insensitive) when provided.
    2. Prefer common major exchanges: NASDAQ, NYSE, NYSE ARCA, NYSE MKT, AMEX.
    3. First remaining ticker for the CIK (stable by row order).

    Returns uppercase ticker string or None when no row matches.
    """
    target = normalize_cik(cik)
    if target is None:
        return None

    matches: list[Mapping[str, Any]] = []
    for row in ticker_rows:
        row_cik = normalize_cik(row.get("cik"))
        ticker = row.get("ticker")
        if row_cik != target or not ticker:
            continue
        matches.append(row)

    if not matches:
        return None

    def _ticker(row: Mapping[str, Any]) -> str:
        return str(row["ticker"]).strip().upper()

    if preferred_exchange:
        pref = preferred_exchange.strip().upper()
        for row in matches:
            ex = str(row.get("exchange") or "").strip().upper()
            if ex == pref:
                return _ticker(row)

    major = {
        "NASDAQ",
        "NYSE",
        "NYSE ARCA",
        "NYSE MKT",
        "AMEX",
        "BATS",
    }
    for row in matches:
        ex = str(row.get("exchange") or "").strip().upper()
        if ex in major:
            return _ticker(row)

    return _ticker(matches[0])


def enterprise_value(
    market_cap: float | None,
    total_debt: float | None,
    cash: float | None,
) -> float | None:
    """Enterprise value = market_cap + total_debt − cash.

    Returns None when market_cap is missing or non-positive.  Missing debt or
    cash are treated as 0.0 (with callers responsible for labeling Explore
    quality when gold fields are sparse).
    """
    if market_cap is None or market_cap <= 0:
        return None
    debt = float(total_debt) if total_debt is not None else 0.0
    cash_val = float(cash) if cash is not None else 0.0
    return market_cap + debt - cash_val


def eod_snapshot(
    price_provider: Any,
    ticker: str,
    as_of: str | date,
    *,
    cik: str | int | None = None,
    include_beta: bool = True,
) -> EodSnapshot:
    """Fetch Explore EOD fields for *ticker* at *as_of* via *price_provider*.

    Parameters
    ----------
    price_provider:
        Instance of :class:`edgar_warehouse.market.price_provider.PriceProvider`
        (or compatible duck-typed object with ``get_price`` / ``get_market_cap``
        / ``get_beta``).
    ticker:
        Trading symbol (yfinance primary key).
    as_of:
        ISO date or ``datetime.date``; last available session ≤ as_of is used.
    cik:
        Optional CIK for consumer join context (not used for the Yahoo fetch).
    include_beta:
        When False, skip the beta call (batch screens that only need close/mcap).
    """
    ticker_u = ticker.strip().upper()
    as_of_str = as_of if isinstance(as_of, str) else as_of.isoformat()
    as_of_str = as_of_str[:10]

    warnings: list[str] = []
    close = price_provider.get_price(ticker_u, as_of_str)
    if close is None:
        warnings.append("close unavailable")

    market_cap = price_provider.get_market_cap(ticker_u, as_of_str)
    if market_cap is None:
        warnings.append("market_cap unavailable")

    beta: float | None = None
    if include_beta:
        beta = price_provider.get_beta(ticker_u)
        if beta is None:
            warnings.append("beta unavailable")

    return EodSnapshot(
        ticker=ticker_u,
        as_of=as_of_str,
        close=close,
        market_cap=market_cap,
        beta=beta,
        source_system=SOURCE_SYSTEM_YAHOO,
        grade=EXPLORE_GRADE,
        cik=normalize_cik(cik),
        warnings=tuple(warnings),
    )


def eod_snapshot_for_cik(
    price_provider: Any,
    ticker_rows: Sequence[Mapping[str, Any]],
    cik: str | int,
    as_of: str | date,
    **kwargs: Any,
) -> EodSnapshot | None:
    """CIK → ticker (TICKER_REFERENCE rows) → :func:`eod_snapshot`.

    Returns None when no ticker can be resolved for *cik*.
    """
    ticker = pick_primary_ticker(ticker_rows, cik)
    if ticker is None:
        return None
    return eod_snapshot(price_provider, ticker, as_of, cik=cik, **kwargs)


def batch_eod_snapshots(
    price_provider: Any,
    tickers: Iterable[str],
    as_of: str | date,
    *,
    include_beta: bool = False,
) -> list[EodSnapshot]:
    """Fetch EOD snapshots for many tickers with one shared *price_provider*.

    Reuse a single :class:`PriceProvider` so in-memory caches apply across the
    batch (ERDP-07 A07.6).  Beta defaults to off for screen-style batches.
    """
    return [
        eod_snapshot(
            price_provider,
            t,
            as_of,
            include_beta=include_beta,
        )
        for t in tickers
    ]
