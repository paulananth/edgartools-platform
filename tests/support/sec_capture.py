"""A raw SEC submissions capture for tests: main documents and the exchange
ticker catalog under `bronze/`, each named by its receipt in `receipts.jsonl`,
as a capture copy holds them."""

import hashlib
import json
from pathlib import Path

CATALOG = "warehouse/bronze/reference/sec/company_tickers_exchange/2026/09/02/company_tickers_exchange.json"


def key(cik: int) -> str:
    return f"warehouse/bronze/submissions/sec/cik={cik}/main/2026/09/29/CIK{cik:010d}.json"


def write_capture(root: Path, documents: dict[int, dict], catalog: dict | None = None) -> tuple[Path, Path]:
    """The capture folder and a population file naming every main document, in order."""
    receipts = []
    named = {key(cik): document for cik, document in documents.items()}
    if catalog is not None:
        named[CATALOG] = catalog
    for name, document in named.items():
        raw = json.dumps(document).encode()
        path = root / "bronze" / name.removeprefix("warehouse/bronze/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        receipts.append({"bytes": len(raw), "key": name, "sha256": hashlib.sha256(raw).hexdigest()})
    (root / "receipts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in receipts))
    population = root / "population.json"
    population.write_text(json.dumps([key(cik) for cik in documents]))
    return root, population
