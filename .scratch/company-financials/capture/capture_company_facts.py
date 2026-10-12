"""Capture the proof cohort's XBRL company facts into a local folder (ticket 04).

    EDGAR_IDENTITY="<name email>" python3 -I capture_company_facts.py <cohort.json> <out folder>

Operator ruling, 2026-10-12 (ticket 02): one bounded capture from SEC's data API,
local proving folder only. At most 5 requests a second (SEC's fair-access limit is
10). A file already captured is skipped. Each response is stored gzipped as
<cik>.json.gz; CAPTURE.json records each CIK's status, raw bytes and the raw
body's sha256. 404 means the entity has no facts. 403 or 429 stops the run. The
run also stops if free disk falls under 2 GB.
"""

import gzip
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
INTERVAL = 0.2  # seconds between requests: 5 a second
MIN_FREE = 2 * 1024**3


def ciks(node) -> list[str]:
    """Every `cik` in the cohort document, in order, once."""
    found = []
    if isinstance(node, dict):
        if "cik" in node:
            found.append(str(node["cik"]))
        for value in node.values():
            if isinstance(value, (dict, list)):
                found += ciks(value)
    elif isinstance(node, list):
        for value in node:
            found += ciks(value)
    return list(dict.fromkeys(found))


def main(cohort: str, out: str) -> int:
    identity = os.environ.get("EDGAR_IDENTITY", "")
    if "@" not in identity:
        raise SystemExit("EDGAR_IDENTITY must name a contact email (SEC requires it in the User-Agent)")
    folder = Path(out).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    ledger_path = folder / "CAPTURE.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {"files": {}}
    started = time.monotonic()
    for cik in ciks(json.loads(Path(cohort).read_text())):
        if ledger["files"].get(cik, {}).get("status") in {"captured", "no facts"}:
            continue
        if shutil.disk_usage(folder).free < MIN_FREE:
            print("stopped: free disk under 2 GB")
            break
        request = urllib.request.Request(URL.format(cik=int(cik)),
                                         headers={"User-Agent": identity, "Accept-Encoding": "identity"})
        time.sleep(INTERVAL)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                ledger["files"][cik] = {"status": "no facts"}
                continue
            ledger["files"][cik] = {"status": f"http {error.code}"}
            if error.code in {403, 429}:
                print(f"stopped: HTTP {error.code} at CIK {cik}")
                break
            continue
        except (urllib.error.URLError, TimeoutError) as error:
            ledger["files"][cik] = {"status": f"error {type(error).__name__}"}
            continue
        (folder / f"{cik}.json.gz").write_bytes(gzip.compress(body))
        ledger["files"][cik] = {"status": "captured", "bytes": len(body),
                                "sha256": hashlib.sha256(body).hexdigest(),
                                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        ledger_path.write_text(json.dumps(ledger, indent=1, sort_keys=True))  # a crash keeps what was captured
    ledger["source"] = URL
    ledger["seconds"] = round(time.monotonic() - started, 1) + ledger.get("seconds", 0)
    ledger_path.write_text(json.dumps(ledger, indent=1, sort_keys=True))
    counts = {}
    for entry in ledger["files"].values():
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    raw = sum(e.get("bytes", 0) for e in ledger["files"].values())
    print(f"{counts}; {raw / 1e6:.0f} MB raw; {ledger['seconds']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
