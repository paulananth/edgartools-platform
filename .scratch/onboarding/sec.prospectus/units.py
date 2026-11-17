"""The capture's units for `sec.prospectus`: the final prospectuses (424B1 to 424B5) listed in the
captured submissions index (`sec.submissions.company`). Local files only, no provider request;
prints counts only.

Every 424B filing is counted by form. A request is written only for the filings named with
`--accession` (the operator permits each SEC request), asking the filing's main document
(`primaryDocument`) in its folder of the SEC archive.

    uv run --no-sync python .scratch/onboarding/sec.prospectus/units.py \
        <submissions capture> <capture folder> --accession <accession> [--accession ...]
"""
import argparse
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts

FORMS = ('424B1', '424B2', '424B3', '424B4', '424B5')
ARCHIVE = 'https://www.sec.gov/Archives/edgar/data/'
RATE = 5  # requests a second, under the SEC's ten
FEED = 'prospectus'


def filings(path):
    document = json.loads(Path(path).read_bytes())
    recent = document.get('filings', {}).get('recent', {})
    return [{'cik': str(document['cik']).zfill(10), 'accession': recent['accessionNumber'][i], 'form': form,
             'year': recent['filingDate'][i][:4], 'document': recent['primaryDocument'][i]}
            for i, form in enumerate(recent.get('form', [])) if form in FORMS]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('submissions', type=Path)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--accession', action='append', default=[])
    args = parser.parse_args()
    with ProcessPoolExecutor(4) as pool:
        rows = sorted((row for part in pool.map(filings, map(str, args.submissions.rglob('*.json')), chunksize=200)
                       for row in part), key=lambda row: (row['cik'], row['accession']))
    by_form, from_2026, seen, wanted = Counter(), Counter(), set(), []
    for row in rows:
        if row['accession'] in seen:
            continue
        seen.add(row['accession'])
        by_form[row['form']] += 1
        from_2026[row['form']] += row['year'] >= '2026'
        if row['accession'] in args.accession and row['document'] and not row['document'].lower().endswith('.paper'):
            wanted.append(row)
    store, root = Artifacts(), args.capture.resolve()
    requested_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    units = []
    for row in wanted:
        folder = row['accession'].replace('-', '')
        scope = {'cik': row['cik'], 'accession_number': row['accession']}
        request = store.put((root / 'requests').as_uri(), {
            'version': 1, 'feed': FEED, 'url': f"{ARCHIVE}{int(row['cik'])}/{folder}/{row['document']}",
            'scope': scope, 'document': 'main', 'requested_at': requested_at, 'requests_per_second': RATE})
        output = (root / 'bronze' / FEED / 'sec' / f"cik={row['cik']}" / folder / 'receipt.json').as_uri()
        units.append({'keys': {'id': row['accession'], 'destination': output, 'feed': FEED, **scope},
                      'input': request, 'output': output, 'cursor': {'offset': 0}})
    manifest = store.put((root / 'manifests').as_uri(), {'version': 1, 'units': units}) if units else None
    print(json.dumps({'filings': dict(sorted(by_form.items())), 'from_2026': dict(sorted(from_2026.items())),
                      'units': len(units), **({'manifest': manifest['uri'], 'manifest_sha256': manifest['sha256']}
                                              if manifest else {})}))


if __name__ == '__main__':
    main()
