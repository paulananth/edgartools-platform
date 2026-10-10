"""Pinned offline census construction on captured samples; no full-population claim."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import time
import zipfile
from urllib.parse import unquote, urlparse

from edgar_warehouse.mdm.clean import name_census, names, gleif_source, store, evidence, primitives
from edgar_warehouse.rules import files, source_engine
from edgar_warehouse.workers import source_mapping
from tests.support import retired_name_census


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while data := stream.read(1024**2):
            h.update(data)
    return h.hexdigest()


class SampleComplete(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--gleif-report', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=1000)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100000:
        parser.error('--limit must be 1..100000')
    started = time.monotonic()
    report = json.loads(args.gleif_report.read_bytes())
    ref = report['archive']
    uri = urlparse(ref['uri'])
    if uri.scheme != 'file' or uri.netloc:
        raise ValueError('require a captured local archive')
    archive = Path(unquote(uri.path))
    receipts = args.capture / 'receipts.jsonl'
    pins = [Path(__file__), args.gleif_report, receipts, archive, Path(name_census.__file__),
            Path(retired_name_census.__file__), Path(names.__file__), Path(gleif_source.__file__),
            Path(source_mapping.__file__), Path(files.__file__), Path(store.__file__),
            Path(evidence.__file__), Path(primitives.__file__), *source_engine.runtime_files(),
            *sorted((files.ROOT / 'sources/gleif').glob('*.yaml')),
            *sorted((files.ROOT / 'sources/sec.submissions.company').glob('*.yaml'))]
    before = {str(p.resolve()): sha(p) for p in pins}
    if sha(archive) != ref['sha256']:
        raise ValueError('GLEIF archive SHA differs')
    rows = []
    def consume(row, index):
        if index != len(rows):
            raise ValueError('ordinal differs')
        rows.append(row)
        if len(rows) == args.limit:
            raise SampleComplete()
    with zipfile.ZipFile(archive) as zipped:
        entries = zipped.infolist()
        if len(entries) != 1 or entries[0].is_dir() or entries[0].flag_bits & 1:
            raise ValueError('archive shape differs')
        with zipped.open(entries[0]) as stream:
            try:
                source_engine.stream_json_array(stream, wrapper='records', on_record=consume,
                    max_bytes=16*1024**3, max_record=1024**2, max_records=10000000)
            except source_engine.SourceRejected as error:
                if error.code != 'stream_consumer' or len(rows) != args.limit:
                    raise
    if len(rows) != args.limit:
        raise ValueError('captured sample is too short')
    refs = [json.loads(line) for line in receipts.read_bytes().splitlines() if line.strip()]
    refs = [r for r in refs if '/submissions/' in r['key'] and '/main/' in r['key']]
    refs.sort(key=lambda r: hashlib.sha256(r['key'].encode()).hexdigest())
    refs = refs[:args.limit]
    if len(refs) != args.limit or len({r['key'] for r in refs}) != args.limit:
        raise ValueError('need distinct SEC captures')
    filers = []
    for ref_sec in refs:
        path = (args.capture / 'bronze' / ref_sec['key'].removeprefix('warehouse/bronze/')).resolve()
        if not path.is_relative_to((args.capture / 'bronze').resolve()):
            raise ValueError('receipt escapes capture')
        data = path.read_bytes()
        if len(data) != ref_sec['bytes'] or hashlib.sha256(data).hexdigest() != ref_sec['sha256']:
            raise ValueError('SEC capture receipt differs')
        raw = json.loads(data)
        filers.append((str(raw['cik']), raw.get('name'),
                       [n.get('name') for n in raw.get('formerNames', [])]))
    # Additional synthetic filers carrying captured GLEIF legal names ensure
    # sampled holder counts are exercised; these are never claimed as SEC facts.
    synthetic = [(f'synthetic-{i}', retired_name_census._text((row.get('Entity') or {}).get('LegalName')), [])
                 for i, row in enumerate(rows)]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr('sample.json', json.dumps({'records':rows}))
    sampled_archive = buffer.getvalue()
    meta = dict(report['metadata'])
    meta['record_count'] = len(rows)
    meta['format'] = 'json.zip'
    all_filers = filers + synthetic
    arguments = dict(filers=all_filers, sec_population={'capture_run_id':'captured-sample', 'filers':len(all_filers)},
                     gleif_metadata=meta, gleif_sha256=hashlib.sha256(sampled_archive).hexdigest())
    source_engine.STEPS = {}
    from tests.mdm.test_clean_name_census import configured
    actual = configured(all_filers, rows, population=arguments['sec_population'],
                        archive_sha256=arguments['gleif_sha256'])
    expected = retired_name_census.build(gleif_archive=io.BytesIO(sampled_archive), **arguments)
    if actual != expected:
        raise ValueError('actual constructed census differs from historical output')
    if before != {str(p.resolve()):sha(p) for p in pins}:
        raise ValueError('qualified runtime/input changed')
    output = {'runtime_pins':before, 'gleif_records':len(rows), 'sec_captures':len(filers),
              'synthetic_filers':len(synthetic), 'constructed_entries':len(actual['entries']),
              'census_digest':hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest(),
              'seconds':time.monotonic()-started,
              'scope':'actual census build and valid EOF on repackaged authenticated samples; synthetic filers explicitly distinguished',
              'whole_source_census_qualified':False, 'installed_population_qualified':False, 'full_goal_complete':False}
    args.output.write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k != 'runtime_pins'}))


if __name__ == '__main__':
    main()
