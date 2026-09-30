"""Ticket 05, step 3: land SEC's ticker catalog from bronze, with no network.

`_sync_reference_data` lands tickers only after a fresh SEC download; a
catalog already in bronze is skipped. This lands the pinned bronze catalog
through the same production pieces that path uses: the parser
(`_parse_company_ticker_rows`), the landing writer
(`SilverLandingStore.replace_company_tickers`) and the export flush
(`write_landing_export`). The landing is what `prepare-clean-company
--ticker-manifest` reads.

    uv run --no-sync python .scratch/company-mastering/research/05-land-tickers.py \\
        <local-bronze-root> <silver-landing-root> <run-id>
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
from edgar_warehouse.serving.silver_landing_writer import write_landing_export
from edgar_warehouse.silver_landing_store import (
    SilverLandingStore,
    _parse_company_ticker_rows,
)

CATALOG = "reference/sec/company_tickers_exchange/2026/09/02/company_tickers_exchange.json"


def main(bronze: str, landing: str, run_id: str) -> None:
    document = json.loads((Path(bronze) / CATALOG).read_text())
    buffer = LandingExportBuffer()
    store = SilverLandingStore(landing_export=buffer)
    written = store.replace_company_tickers(
        _parse_company_ticker_rows(document),
        run_id,
        source_name="company_tickers_exchange",
    )
    counts = write_landing_export(
        buffer,
        StorageLocation(landing),
        run_id=run_id,
        business_date="2026-09-02",
        command_name="reference-catalog",
        environment_name="local",
        now=datetime.now(UTC),
    )
    print(json.dumps({"written": written, "counts": counts}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
