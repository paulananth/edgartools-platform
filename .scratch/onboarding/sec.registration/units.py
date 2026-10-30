"""Ticket 149: the capture's units, one frozen request per S-1 or F-1 original, from the
captured submissions index (`sec.submissions.company`). Local files only, no provider request;
prints counts only.

A request asks the filing's main document (`primaryDocument`) in its folder of the SEC
archive. A filing listed under two co-registrants is asked once, under the first CIK in
order. A filing that names no document, or a paper one, has nothing to ask and is counted.

    uv run --no-sync python .scratch/onboarding/sec.registration/units.py \
        <submissions capture> <capture folder> [--limit N]
"""
import argparse
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts

FORMS = ('S-1', 'F-1')
ARCHIVE = 'https://www.sec.gov/Archives/edgar/data/'
RATE = 5  # requests a second, under the SEC's ten


def filings(path):
    document = json.loads(Path(path).read_bytes())
    recent = document.get('filings', {}).get('recent', {})
    return [{'cik': str(document['cik']).zfill(10), 'accession': recent['accessionNumber'][i],
             'document': recent['primaryDocument'][i]}
            for i, form in enumerate(recent.get('form', [])) if form in FORMS]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('submissions', type=Path)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    with ProcessPoolExecutor(4) as pool:
        rows = sorted((row for part in pool.map(filings, map(str, args.submissions.rglob('*.json')), chunksize=200)
                       for row in part), key=lambda row: (row['cik'], row['accession']))
    counted, seen, wanted = Counter(), set(), []
    for row in rows:
        if row['accession'] in seen:
            counted['listed twice'] += 1
        elif not row['document'] or row['document'].lower().endswith('.paper'):
            counted['no electronic document'] += 1
        else:
            seen.add(row['accession'])
            wanted.append(row)
    wanted = wanted[:args.limit] if args.limit else wanted
    store, root = Artifacts(), args.capture.resolve()
    requested_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    units = []
    for row in wanted:
        folder = row['accession'].replace('-', '')
        scope = {'cik': row['cik'], 'accession': row['accession']}
        request = store.put((root / 'requests').as_uri(), {
            'version': 1, 'feed': 'registration', 'url': f"{ARCHIVE}{int(row['cik'])}/{folder}/{row['document']}",
            'scope': scope, 'document': 'main', 'requested_at': requested_at, 'requests_per_second': RATE})
        output = (root / 'bronze' / 'registration' / 'sec' / f"cik={row['cik']}" / folder / 'receipt.json').as_uri()
        units.append({'keys': {'id': row['accession'], 'destination': output, 'feed': 'registration', **scope},
                      'input': request, 'output': output, 'cursor': {'offset': 0}})
    manifest = store.put((root / 'manifests').as_uri(), {'version': 1, 'units': units})
    print(json.dumps({'listed': len(rows), **counted, 'units': len(units), 'manifest': manifest['uri'],
                      'manifest_sha256': manifest['sha256']}))


if __name__ == '__main__':
    main()
