#!/usr/bin/env python3
"""Ask OpenFIGI about the tickers silver names that no Security holds, as a capture the OpenFIGI load reads.

    openfigi_ticker_capture.py <capture folder> --column silver.registration_offering.ticker [--column ...]
                               --sec-tickers <the SEC's company_tickers_exchange.json>
    openfigi_ticker_capture.py <capture folder> --send

It reads the store in STORES' worker.env, read-only: the distinct values of each column named, written as a Security
holds its ticker (letters and digits, upper case), less every ticker a Security already holds. It writes them into a
new capture folder as OpenFIGI mapping jobs (TICKER, exchange US), 100 to a request file under `id_ticker/`, with a
copy of the SEC's ticker file, which the OpenFIGI source extract reads beside the answers. It prints counts only.

`--send` then posts each request of that folder to OpenFIGI's mapping API, under the feed's approved URL prefix and with its key
read from OPENFIGI_API_KEY for that request only, keeps each answer beside its request, and writes `receipts.jsonl`.
Each run is a request to a data provider: run it only with the operator's permission for it. A capture folder is
written once, never replaced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Callable, Iterable

FOLDER = "id_ticker"
BATCH = 100
SEC_TICKERS = "company_tickers_exchange"
MAPPING = "https://api.openfigi.com/v3/mapping"
RECEIPTS = "receipts.jsonl"


def held_form(ticker: str) -> str:
    """A ticker as a Security holds it: letters and digits, upper case (BRK.B and BRKB meet)."""
    return re.sub(r"[^A-Za-z0-9]", "", ticker).upper()


def wanted(stated: Iterable[str | None], held: set[str]) -> list[str]:
    """Each ticker stated, upper case and as written (OpenFIGI writes a class ticker with its separator), that no
    Security holds."""
    return sorted({value.strip().upper() for value in stated if value and held_form(value) and held_form(value) not in held})


def canonical(jobs: list[dict]) -> bytes:
    return json.dumps(jobs, sort_keys=True, separators=(",", ":")).encode()


def write(folder: Path, tickers: list[str], sec_tickers: Path) -> int:
    """The request files of a new capture folder, and the SEC's ticker file beside them; the number of requests."""
    (folder / FOLDER).mkdir(parents=True, exist_ok=False)
    batches = [tickers[start:start + BATCH] for start in range(0, len(tickers), BATCH)]
    for number, batch in enumerate(batches):
        jobs = [{"idType": "TICKER", "idValue": ticker, "exchCode": "US"} for ticker in batch]
        (folder / FOLDER / f"{number:05d}.request.json").write_bytes(canonical(jobs))
    copy = sec_file(sec_tickers)
    (folder / copy).parent.mkdir(parents=True)
    shutil.copyfile(sec_tickers, folder / copy)
    return len(batches)


def sec_file(path: Path) -> str:
    """Where the SEC's ticker file sits in a capture: its path from its dated `company_tickers_exchange` folder on, as
    the SEC capture keeps it, so the file's date stays with it."""
    parts = path.resolve().parts
    if SEC_TICKERS not in parts[:-1]:
        raise ValueError(f"{path} is not in a dated {SEC_TICKERS} folder")
    return "/".join(parts[len(parts) - 1 - parts[::-1].index(SEC_TICKERS):])


def receipt(folder: Path, file: str, beside: Path | None = None) -> dict:
    body = (folder / file).read_bytes()
    row = {"file": file, "status": 200, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    return {**row, "request_sha256": hashlib.sha256(beside.read_bytes()).hexdigest()} if beside else row


def send(folder: Path, post: Callable[[bytes], bytes]) -> list[dict]:
    """Each request posted once, its answer kept beside it; then the receipts, once every answer answers every job."""
    rows = []
    for request in sorted((folder / FOLDER).glob("*.request.json")):
        body = request.read_bytes()
        answer = post(body)
        asked, answered = len(json.loads(body)), len(json.loads(answer))
        if answered != asked:
            raise ValueError(f"{request.name}: OpenFIGI answers {answered} of {asked} jobs")
        name = request.name.replace(".request.json", ".json")
        (folder / FOLDER / name).write_bytes(answer)
        rows.append(receipt(folder, f"{FOLDER}/{name}", request))
    rows += [receipt(folder, path.relative_to(folder).as_posix()) for path in sorted((folder / SEC_TICKERS).rglob("*.json"))]
    with (folder / RECEIPTS).open("x") as out:
        out.writelines(json.dumps(row) + "\n" for row in rows)
    return rows


def stated_and_held(columns: list[str]) -> tuple[list[str], set[str]]:
    """The values of each `schema.table.column`, and every ticker a Security holds, read only."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills/data-operations/scripts"))
    import load_jobs
    import psycopg

    url = load_jobs.data_url(load_jobs.load_env(load_jobs.STORES / "worker.env")).replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as conn:
        stated = []
        for column in columns:
            schema, table, name = column.split(".")
            stated += [v for (v,) in conn.execute(f'select distinct "{name}" from "{schema}"."{table}"')]
        held = {v for (v,) in conn.execute(
            "select distinct i.value from mdm.mastering_identifier i join mdm.mastering_master m "
            "on m.entity_id = i.entity_id and m.kind = 'security' where i.namespace = 'ticker'")}
    return stated, held


def poster() -> Callable[[bytes], bytes]:
    """A POST to OpenFIGI's mapping API as the OpenFIGI feed's acquisition authority allows it."""
    from edgar_warehouse.rules import files
    from edgar_warehouse.workers import provider_capture, provider_transport as transport

    feed = files.source("openfigi")["acquisition"]["feeds"]["mapping"]
    url = transport.approved_url(MAPPING, feed["url_prefixes"], feed["capabilities"]["fetch"])

    def post(body: bytes) -> bytes:
        method, sent, headers = provider_capture.sending(feed, {"body": json.loads(body)})
        if sent != body:
            raise ValueError("The request sent differs from the request kept")
        return transport.fetch(url, "edgartools-platform", max_bytes=feed["completeness"]["max_bytes"],
                               requests_per_second=4, before_request=lambda: None, method=method, body=sent,
                               extra_headers=headers).content
    return post


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--column", action="append", help="schema.table.column of a ticker in silver")
    parser.add_argument("--sec-tickers", type=Path)
    parser.add_argument("--send", action="store_true", help="post the requests of a folder already written")
    args = parser.parse_args(argv)
    if args.send:
        rows = send(args.folder, poster())
        print(f"answers kept {len(rows) - 1}, receipts {len(rows)}")
        return 0
    if not args.column or not args.sec_tickers:
        parser.error("writing a capture needs --column and --sec-tickers")
    stated, held = stated_and_held(args.column)
    tickers = wanted(stated, held)
    requests = write(args.folder, tickers, args.sec_tickers)
    print(f"stated {len({v for v in stated if v})}, held by a Security {len(held)}, asked {len(tickers)} in {requests} requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
