"""Receipt-pinned name-key parity; offline, no activation or mastering claim."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

import yaml
from edgar_warehouse.mdm.clean import names
from edgar_warehouse.rules import source_engine


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(engine, values, oracle):
    data = json.dumps({'names': [{'name': value} for value in values]}, ensure_ascii=False).encode()
    reading = engine.read(data)
    if reading.deferred or len(reading.tables['names']) != len(values):
        raise ValueError('Names missing or deferred')
    keys = [row['key'] for row in reading.tables['names']]
    expected = [oracle(value) for value in values]
    if keys != expected:
        index = next(i for i, pair in enumerate(zip(keys, expected)) if pair[0] != pair[1])
        raise ValueError(f'Name key differs: {values[index]!r}: {keys[index]!r} != {expected[index]!r}')
    return keys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=1000)
    parser.add_argument('--unicode', action='store_true', help='Compare every Unicode scalar in both recipes')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error('--limit must be 1..1000')
    started = time.monotonic()
    root = Path(__file__).resolve().parents[2]
    capture = args.capture.resolve()
    receipts = capture / 'receipts.jsonl'
    refs = [json.loads(line) for line in receipts.read_bytes().splitlines() if line.strip()]
    refs = [ref for ref in refs if '/submissions/' in ref['key'] and '/main/' in ref['key']]
    refs.sort(key=lambda ref: hashlib.sha256(ref['key'].encode()).hexdigest())
    refs = refs[:args.limit]
    if len(refs) != args.limit or len({ref['key'] for ref in refs}) != args.limit:
        raise ValueError('Need requested distinct receipt-pinned main captures')
    paths = [root / 'rules/sources/sec.submissions.company/name-key.yaml', root / 'rules/sources/gleif/name-key.yaml']
    contracts = [yaml.safe_load(path.read_text()) for path in paths]
    engines = [source_engine.SourceEngine(contract) for contract in contracts]
    pinned = [Path(__file__), Path(names.__file__), *source_engine.runtime_files(), *paths, receipts]
    before = {str(path): sha(path) for path in pinned}
    # Fail if a recipe ever starts requiring registered custom callbacks.
    if any('custom' in json.dumps(contract) for contract in contracts):
        raise ValueError('Name-key recipe must use native configuration only')
    evidence, count, digest = [], 0, hashlib.sha256()
    for ref in refs:
        path = (capture / 'bronze' / ref['key'].removeprefix('warehouse/bronze/')).resolve()
        if not path.is_relative_to(capture / 'bronze'):
            raise ValueError('Capture path escapes bronze')
        data = path.read_bytes()
        if len(data) != ref['bytes'] or hashlib.sha256(data).hexdigest() != ref['sha256']:
            raise ValueError(f"Capture receipt mismatch: {ref['key']}")
        raw = json.loads(data)
        values = [raw.get('name'), *[row.get('name') for row in raw.get('formerNames', [])]]
        keys = verify(engines[0], values, names.sec_legal_form_key)
        verify(engines[1], values, names.legal_form_key)
        digest.update(json.dumps(keys, ensure_ascii=False, separators=(',', ':')).encode() + b'\n')
        evidence.append({'key': ref['key'], 'sha256': ref['sha256'], 'names': len(values)})
        count += len(values)
    scalar_count = 0
    if args.unicode:
        for start in range(0, 0x110000, 4096):
            values = [chr(n) for n in range(start, min(start + 4096, 0x110000)) if not 0xD800 <= n <= 0xDFFF]
            if not values:
                continue
            for engine, oracle in zip(engines, [names.sec_legal_form_key, names.legal_form_key]):
                verify(engine, values, oracle)
            scalar_count += len(values)
    fault = deepcopy(contracts[0])
    del fault['read']['tables']['names']['columns']['key']['text']['transforms'][1]
    fault_engine = source_engine.SourceEngine(fault)
    try:
        verify(fault_engine, ['A INC /DE/'], names.sec_legal_form_key)
    except ValueError:
        fault_detected = True
    else:
        raise ValueError('Deliberate state-suffix fault was not detected')
    if before != {str(path): sha(path) for path in pinned}:
        raise ValueError('Qualification code, input receipt or contract changed during run')
    result = {'captures': len(refs), 'names': count, 'unicode_scalars': scalar_count,
              'exact_key_parity': True, 'deliberate_state_suffix_fault_detected': fault_detected,
              'sec_keys_sha256': digest.hexdigest(), 'inputs_and_code_sha256': before,
              'full_company_mastering': False, 'census_population_qualified': False,
              'elapsed_seconds': round(time.monotonic() - started, 3), 'evidence': evidence}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key not in {'evidence', 'inputs_and_code_sha256'}}))


if __name__ == '__main__':
    main()
