"""Build the three CIK cohort lists used by the phased bootstrap pipeline.

Cohort 1 — S&P 500         (~500 CIKs): sp500_ciks.json
Cohort 2 — S&P 400 + 600   (~1,000 CIKs): sp500_1500_ciks.json
Cohort 3 — Remaining       (~6,100 CIKs): remaining_ciks.json

Sources:
  Primary   — Wikipedia S&P index pages (pd.read_html, no auth required)
  Validator — GitHub datasets/s-and-p-500-companies (CC0 licence)
  Universe  — edgar bundled company_tickers.parquet (Nasdaq + NYSE + CBOE only)

Usage:
  python -m edgar_warehouse.scripts.build_cohort_lists \\
      --output-dir /tmp/cohorts
  # or S3:
  python -m edgar_warehouse.scripts.build_cohort_lists \\
      --output-dir s3://my-bucket/reference/cohorts
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Wikipedia source URLs
# ---------------------------------------------------------------------------
_SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_SP400_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
_SP600_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"

# GitHub cross-validation dataset (CC0)
_SP500_GITHUB_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies"
    "/main/data/constituents.csv"
)

# Target exchanges for the company universe (OTC excluded)
_EXCHANGE_LISTED = frozenset({"Nasdaq", "NYSE", "CBOE"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_universe() -> "pd.DataFrame":
    """Load exchange-listed companies from bundled company_tickers.parquet."""
    import pandas as pd
    from edgar.reference.tickers import get_company_tickers

    df: pd.DataFrame = get_company_tickers(as_dataframe=True)

    if "exchange" not in df.columns:
        # Older parquet without exchange column — use full set as fallback
        log.warning("company_tickers has no 'exchange' column; universe includes all entries")
        return df.rename(columns={"company": "name"})

    before = len(df)
    df = df[df["exchange"].isin(_EXCHANGE_LISTED)].copy()
    log.info("Universe: %d exchange-listed companies (dropped %d OTC)", len(df), before - len(df))
    return df.rename(columns={"company": "name"})


def _wiki_tickers(url: str, *, retries: int = 3) -> list[str]:
    """Scrape ticker symbols from a Wikipedia S&P index table."""
    import pandas as pd

    for attempt in range(1, retries + 1):
        try:
            tables = pd.read_html(url, attrs={"id": "constituents"})
            if not tables:
                tables = pd.read_html(url)
            tbl = tables[0]
            # Column name varies by page: 'Symbol', 'Ticker symbol'
            for col in ("Symbol", "Ticker symbol", "Ticker"):
                if col in tbl.columns:
                    return [t.strip().replace(".", "-") for t in tbl[col].dropna()]
            raise ValueError(f"No ticker column found in Wikipedia table at {url}. "
                             f"Columns: {list(tbl.columns)}")
        except Exception as exc:
            if attempt == retries:
                raise
            log.warning("Wikipedia fetch attempt %d/%d failed (%s); retrying…", attempt, retries, exc)
            time.sleep(2 ** attempt)
    return []  # unreachable


def _github_sp500_tickers() -> set[str]:
    """Cross-validation set from GitHub datasets/s-and-p-500-companies (CC0)."""
    import pandas as pd

    try:
        df = pd.read_csv(_SP500_GITHUB_URL, usecols=["Symbol"])
        return {t.strip().replace(".", "-") for t in df["Symbol"].dropna()}
    except Exception as exc:
        log.warning("GitHub cross-validation fetch failed (%s); proceeding without it", exc)
        return set()


def _tickers_to_ciks(tickers: list[str], universe: "pd.DataFrame") -> list[int]:
    """Map ticker symbols to CIKs using the exchange-listed universe."""
    import pandas as pd

    ticker_map: dict[str, int] = dict(
        zip(universe["ticker"].str.upper(), universe["cik"].astype(int))
    )
    ciks = []
    missing = []
    for t in tickers:
        cik = ticker_map.get(t.upper())
        if cik is not None:
            ciks.append(cik)
        else:
            missing.append(t)

    if missing:
        log.warning(
            "%d tickers had no CIK match in universe (likely OTC or de-listed): %s",
            len(missing),
            missing[:20],
        )
    return sorted(set(ciks))


def _write_json(data: Any, path_str: str) -> None:
    """Write JSON to a local path or S3 URI."""
    if path_str.startswith("s3://"):
        _write_s3_json(data, path_str)
    else:
        dest = Path(path_str)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, indent=2))
        log.info("Wrote %d items to %s", len(data), dest)


def _write_s3_json(data: Any, s3_uri: str) -> None:
    import boto3

    # Parse s3://bucket/key
    without_proto = s3_uri[5:]
    bucket, _, key = without_proto.partition("/")
    body = json.dumps(data, indent=2).encode()
    boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    log.info("Uploaded %d items to %s", len(data), s3_uri)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_cohort_lists(output_dir: str) -> None:
    """Fetch S&P index constituents and write three CIK cohort lists."""
    log.info("Loading company universe from edgar bundled parquet…")
    universe = _load_universe()

    # ── Cohort 1: S&P 500 ──────────────────────────────────────────────────
    log.info("Fetching S&P 500 from Wikipedia…")
    sp500_tickers_wiki = _wiki_tickers(_SP500_WIKI_URL)
    sp500_tickers_github = _github_sp500_tickers()

    # Cross-validate: warn on divergence > 5%
    wiki_set = set(sp500_tickers_wiki)
    github_set = sp500_tickers_github
    if github_set:
        only_wiki = wiki_set - github_set
        only_github = github_set - wiki_set
        if only_wiki or only_github:
            log.warning(
                "S&P 500 cross-validation gap: %d only-in-Wikipedia, %d only-in-GitHub",
                len(only_wiki), len(only_github),
            )
            log.debug("Only in Wikipedia: %s", sorted(only_wiki)[:20])
            log.debug("Only in GitHub: %s", sorted(only_github)[:20])
        else:
            log.info("S&P 500 cross-validation: perfect agreement (%d tickers)", len(wiki_set))

    # Use Wikipedia as authoritative; GitHub confirms membership
    sp500_ciks = _tickers_to_ciks(sp500_tickers_wiki, universe)
    log.info("Cohort 1 (S&P 500): %d CIKs", len(sp500_ciks))

    # ── Cohort 2: S&P 400 + S&P 600 ────────────────────────────────────────
    log.info("Fetching S&P 400 and S&P 600 from Wikipedia…")
    sp400_tickers = _wiki_tickers(_SP400_WIKI_URL)
    sp600_tickers = _wiki_tickers(_SP600_WIKI_URL)

    sp400_ciks = _tickers_to_ciks(sp400_tickers, universe)
    sp600_ciks = _tickers_to_ciks(sp600_tickers, universe)

    # Deduplicate across cohort 1 (some tickers move between indices mid-year)
    sp500_set = set(sp500_ciks)
    sp1500_ciks = sorted(set(sp400_ciks + sp600_ciks) - sp500_set)
    log.info(
        "Cohort 2 (S&P 400 + 600): %d CIKs (S&P 400=%d, S&P 600=%d, after dedup vs C1)",
        len(sp1500_ciks), len(sp400_ciks), len(sp600_ciks),
    )

    # ── Cohort 3: Remaining exchange-listed ─────────────────────────────────
    all_sp_ciks = sp500_set | set(sp1500_ciks)
    remaining_ciks = sorted(
        int(cik) for cik in universe["cik"] if int(cik) not in all_sp_ciks
    )
    log.info("Cohort 3 (remaining): %d CIKs", len(remaining_ciks))

    total = len(sp500_ciks) + len(sp1500_ciks) + len(remaining_ciks)
    log.info(
        "Total universe: %d CIKs (S&P 500=%d, S&P 400+600=%d, remaining=%d)",
        total, len(sp500_ciks), len(sp1500_ciks), len(remaining_ciks),
    )

    # ── Write outputs ────────────────────────────────────────────────────────
    _write_json(sp500_ciks,    f"{output_dir.rstrip('/')}/sp500_ciks.json")
    _write_json(sp1500_ciks,   f"{output_dir.rstrip('/')}/sp500_1500_ciks.json")
    _write_json(remaining_ciks, f"{output_dir.rstrip('/')}/remaining_ciks.json")

    log.info("Done. Three cohort files written to %s", output_dir)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Build CIK cohort lists for phased bootstrap pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        metavar="PATH",
        help="Local directory or S3 URI prefix for output JSON files",
    )
    args = parser.parse_args(argv)
    build_cohort_lists(args.output_dir)


if __name__ == "__main__":
    _main(sys.argv[1:])
