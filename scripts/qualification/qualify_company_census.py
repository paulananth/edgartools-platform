"""Offline pinned census reuse and captured-name evidence; no mastering claim."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import time

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm.clean import company_source, name_census, names
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare

ZERO = '0' * 64


def bind(value, sha):
    if isinstance(value, str): return sha if value == ZERO else value
    if isinstance(value, list): return [bind(item, sha) for item in value]
    if isinstance(value, dict): return {key: bind(item, sha) for key, item in value.items()}
    return value


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(store, root, label, config, body):
    raw = store.put(root.as_uri(), body)
    contract = store.put(root.as_uri(), config)
    manifest = store.put(root.as_uri(), {'version': 1, 'contract': contract, 'artifacts': [raw]})
    task = {'input': manifest, 'output': (root / f'{label}.json').as_uri(), 'checks': ['source.output']}
    result = source_read.execute(task, store)
    if source_read.verify({**task, 'candidate': result}, store) != ({'source.output': True}, []):
        raise ValueError('Reading verification failed')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--census', type=Path, required=True)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=1000)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000: parser.error('--limit must be 1..1000')
    started = time.monotonic()
    rules = files.ROOT / 'sources/sec.submissions.company'
    receipts = args.capture / 'receipts.jsonl'
    pinned = [Path(__file__), args.census, receipts,
              rules / 'census.yaml', rules / 'name-key.yaml', rules / 'combine-census.yaml',
              Path(company_source.__file__), Path(name_census.__file__), Path(names.__file__),
              Path(name_census.cascaded.__file__),
              Path(source_combine.__file__), Path(mdm_prepare.__file__),
              Path(source_read.__file__), *source_read.runtime_files(),
              *source_combine.runtime_files(), *mdm_prepare.runtime_files()]
    before = {str(path): sha(path) for path in pinned}
    census = json.loads(args.census.read_bytes())
    refs = [json.loads(line) for line in receipts.read_bytes().splitlines() if line.strip()]
    refs = [ref for ref in refs if '/submissions/' in ref['key'] and '/main/' in ref['key']]
    refs.sort(key=lambda ref: hashlib.sha256(ref['key'].encode()).hexdigest())
    refs = refs[:args.limit]
    if len(refs) != args.limit or len({ref['key'] for ref in refs}) != args.limit:
        raise ValueError('Need requested distinct captures')
    captured, evidence = [], []
    for ref in refs:
        path = (args.capture / 'bronze' / ref['key'].removeprefix('warehouse/bronze/')).resolve()
        if not path.is_relative_to((args.capture / 'bronze').resolve()):
            raise ValueError('Capture escapes bronze')
        data = path.read_bytes()
        if len(data) != ref['bytes'] or hashlib.sha256(data).hexdigest() != ref['sha256']:
            raise ValueError('Capture receipt differs')
        raw = json.loads(data)
        captured.append({'cik': int(raw['cik']), 'name': raw.get('name')})
        evidence.append({'key': ref['key'], 'sha256': ref['sha256']})
    store = Artifacts()
    with tempfile.TemporaryDirectory(prefix='census-qualification-') as directory:
        root = Path(directory)
        raw = store.put(root.as_uri(), census)
        config = bind(files.load(rules / 'census.yaml'), raw['sha256'])
        census_ref = read(store, root, 'census', config, census)
        tables = store.json(census_ref)['artifacts'][0]['tables']
        expected = [{'name_key': key, 'census_digest': raw['sha256'],
                     'name_evidence': {'census': raw['sha256'], 'version': census['version'], 'key': key, **value}}
                    for key, value in sorted(census['entries'].items()) if key and value is not None]
        if digest(tables['names']) != digest(expected):
            raise ValueError('Full census entries differ in values or types')
        expected_cascade = [{'cik': int(key), 'census_digest': raw['sha256'],
                            'cascade_evidence': {'census': raw['sha256'], 'version': census['cascade']['version'], **value}}
                           for key, value in sorted(census.get('cascade', {}).get('assignments', {}).items()) if value is not None]
        if digest(tables['cascade']) != digest(expected_cascade): raise ValueError('Cascade entries differ')
        # Mechanically extracted captured names are a derived qualification artifact.
        # This does not substitute for full main/pagination/provenance qualification.
        name_config = files.load(rules / 'name-key.yaml')
        columns = name_config['read']['tables']['names']['columns']
        columns['cik'] = {'integer': {'path': 'cik', 'on_invalid': 'error'}}
        columns['_name_key'] = columns.pop('key')
        names_ref = read(store, root, 'names', name_config, {'names': captured})
        template = bind(files.load(rules / 'combine-census.yaml'), raw['sha256'])
        combine = {'execution': {'profile': 'source.combine'}, 'combine': {
            'max_rows': 100000,
            'groups': {key: value for key, value in template['combine']['groups'].items() if key.startswith('census_')},
            'tables': {'company': {'source': 'main', 'table': 'names', 'checks': {}, 'where': {},
                'joins': {key: value for key, value in template['combine']['tables']['company']['joins'].items()
                          if key in ('name_census', 'cascade_evidence')}, 'drop': ['_name_key']}}}}
        refs_manifest = store.put(root.as_uri(), {'version': 1, 'contract': store.put(root.as_uri(), combine),
                                                  'readings': {'main': names_ref, 'census': census_ref}})
        task = {'input': refs_manifest, 'output': (root / 'combined.json').as_uri(), 'checks': ['source.combined']}
        combined = source_combine.execute(task, store)
        if source_combine.verify({**task, 'candidate': combined}, store) != ({'source.combined': True}, []):
            raise ValueError('Combination verification failed')
        actual = store.json(combined)['artifacts'][0]['tables']['company']
        expected = [{'name': row['name'], 'cik': row['cik'], 'name_census':
                     company_source._census_evidence(census, {'entity_name': row['name'], 'cik': row['cik']}, raw['sha256'])}
                    for row in captured]
        if digest(actual) != digest(expected): raise ValueError('Captured-name census evidence differs')
        prepare = {'input': combined, 'output': (root / 'prepared/manifest.json').as_uri(), 'checks': ['mdm.prepared'],
                   'keys': {'table': 'company', 'dataset': 'sec.submissions.company.v1', 'policy': ZERO,
                            'consumer': 'qualification', 'batch_id': 'census', 'as_of': '2026-10-07T00:00:00Z'}}
        prepared = mdm_prepare.execute(prepare, store)
        if mdm_prepare.verify({**prepare, 'candidate': prepared}, store) != ({'mdm.prepared': True}, []):
            raise ValueError('Preparation verification failed')
        prepared_rows = []
        for batch in store.json(prepared)['batches']:
            data = (root / 'prepared' / batch['input']['path']).read_bytes()
            if hashlib.sha256(data).hexdigest() != batch['input']['sha256']: raise ValueError('Prepared batch hash differs')
            prepared_rows.extend(json.loads(line) for line in data.splitlines())
        if digest(prepared_rows) != digest(expected): raise ValueError('Prepared name evidence differs')
        wrong = deepcopy(config)
        wrong['execution']['input_sha256s'] = ['1' * 64]
        try: read(store, root, 'fault', wrong, census)
        except ValueError as error:
            if 'approved artifact hash' not in str(error): raise
        else: raise ValueError('Deliberate input substitution not refused')
        if (root / 'fault.json').exists(): raise ValueError('Fault published output')
        if before != {str(path): sha(path) for path in pinned}: raise ValueError('Pinned implementation changed')
        result = {'census_entries': len(tables['names']), 'cascade_entries': len(tables['cascade']),
                  'captures': len(captured), 'exact_evidence_and_preparation_parity': True,
                  'input_substitution_refused_before_publication': True, 'canonical_census_sha256': raw['sha256'],
                  'evidence_sha256': digest(expected), 'inputs_and_code_sha256': before,
                  'census_construction_qualified': False, 'full_company_mastering': False,
                  'full_main_pagination_provenance_qualified': False, 'installed_bundle_qualified': False,
                  'elapsed_seconds': round(time.monotonic() - started, 3), 'evidence': evidence}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key not in ('evidence', 'inputs_and_code_sha256')}))


if __name__ == '__main__': main()
