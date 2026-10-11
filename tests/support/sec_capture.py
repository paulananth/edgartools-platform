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


def address(street="1 MAIN ST", city="NEW YORK", state="NY", zip_code="10019", country=None, country_code=None):
    return {"street1": street, "street2": None, "city": city, "stateOrCountry": state, "zipCode": zip_code,
            "stateOrCountryDescription": state, "isForeignLocation": 1 if country_code else 0,
            "foreignStateTerritory": None, "country": country, "countryCode": country_code}


def document(cik: int, name: str, *, entity_type="operating", forms=("10-K",), business=None, former=(),
             category="Large accelerated filer") -> dict:
    """A main submissions document in SEC's shape, with only what a test sets."""
    recent = {field: [] for field in (
        "accessionNumber", "filingDate", "reportDate", "acceptanceDateTime", "act", "form", "fileNumber",
        "filmNumber", "items", "core_type", "size", "isXBRL", "isInlineXBRL", "isXBRLNumeric",
        "primaryDocument", "primaryDocDescription")}
    for n, form in enumerate(forms):
        values = {"accessionNumber": f"{cik:010d}-26-{n:06d}", "filingDate": "2026-01-02", "reportDate": "",
                  "acceptanceDateTime": "2026-01-02T16:00:00.000Z", "act": "34", "form": form,
                  "fileNumber": "001-00001", "filmNumber": "1", "items": "", "core_type": form, "size": 1,
                  "isXBRL": 0, "isInlineXBRL": 0, "isXBRLNumeric": 0, "primaryDocument": "a.htm",
                  "primaryDocDescription": form}
        for field, value in values.items():
            recent[field].append(value)
    return {"cik": f"{cik:010d}", "entityType": entity_type, "sic": "7372", "sicDescription": "Services",
            "ownerOrg": "", "insiderTransactionForOwnerExists": 0, "insiderTransactionForIssuerExists": 1,
            "name": name, "tickers": [], "exchanges": [], "ein": "123456789", "lei": None, "description": "",
            "website": "", "investorWebsite": "", "category": category, "fiscalYearEnd": "0930",
            "stateOfIncorporation": "DE", "stateOfIncorporationDescription": "DE",
            "addresses": {"mailing": address(), **({"business": business} if business is not None else {})},
            "phone": "", "flags": "", "formerNames": [{"name": n, "from": "2000-01-01T00:00:00.000Z",
                                                        "to": "2010-01-01T00:00:00.000Z"} for n in former],
            "filings": {"recent": recent, "files": []}}


def catalog(*rows: tuple[int, str, str, str]) -> dict:
    """SEC's exchange ticker catalog: (cik, name, ticker, exchange) rows, in rank order."""
    return {"fields": ["cik", "name", "ticker", "exchange"], "data": [list(row) for row in rows]}
