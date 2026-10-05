"""Bounded offline raw Company address comparison; no full mastering claim."""
from __future__ import annotations
import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import digest
from tests.support.retired_submission_loaders.bronze_submission_extractors import stage_address_loader
from edgar_warehouse.mdm.clean.company_source import business_address
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error('--limit must be 1..1000')
    started = time.monotonic()
    root = args.capture.resolve()
    receipts = (root / 'receipts.jsonl').read_bytes()
    refs = [json.loads(line) for line in receipts.splitlines() if line.strip()]
    refs = [ref for ref in refs if '/submissions/' in ref['key'] and '/main/' in ref['key']]
    refs.sort(key=lambda ref: hashlib.sha256(ref['key'].encode()).hexdigest())
    selected = refs[:args.limit]
    if len(selected) != args.limit or len({ref['key'] for ref in selected}) != args.limit:
        raise ValueError('Need requested distinct receipt-pinned captures')
    store, evidence, present = Artifacts(), [], 0
    contract_body = files.load(args.contract)
    with tempfile.TemporaryDirectory(prefix='codex-company-address-') as folder:
        scratch = Path(folder)
        contract = store.put(scratch.as_uri(), contract_body)
        for n in range(0, len(selected), 2):
            inputs, expected_rows = [], []
            for ref in selected[n:n + 2]:
                path = (root / 'bronze' / ref['key'].removeprefix('warehouse/bronze/')).resolve()
                if not path.is_relative_to(root / 'bronze'):
                    raise ValueError('Receipt key escapes capture root')
                raw = {'uri': path.as_uri(), 'sha256': ref['sha256']}
                payload = json.loads(store.verified(raw, max_bytes=32 * 1024**2))
                old_rows = stage_address_loader(payload, int(payload['cik']), 'qualification', ref['sha256'], 'default')
                old = [business_address(row) for row in old_rows if row['address_type'] == 'business']
                inputs.append(raw)
                expected_rows.append((ref, old))
            manifest = store.put(scratch.as_uri(), {'version': 1, 'contract': contract, 'artifacts': inputs})
            work = {'input': manifest, 'output': (scratch / f'reading-{n // 2}.json').as_uri(), 'checks': ['source.output']}
            result = source_read.execute(work, store)
            if source_read.verify({**work, 'candidate': result}, store) != ({'source.output': True}, []):
                raise ValueError('Source worker verification failed')
            read = store.json(result)
            if len(read['artifacts']) != len(inputs):
                raise ValueError('Reading artifact count differs from frozen scope')
            for artifact, raw, (ref, old) in zip(read['artifacts'], inputs, expected_rows):
                rows = artifact['tables']['addresses']
                actual = rows[0]['business_address'] if rows else None
                expected = old[-1] if old else None
                if artifact['input'] != raw or len(rows) != len(old) or actual != expected or artifact['deferred']:
                    raise ValueError(f"Raw Company address differs: {ref['key']}")
                present += int(bool(old))
                evidence.append({'key': ref['key'], 'input_sha256': ref['sha256'], 'address_sha256': digest(actual), 'present': bool(old)})
    result = {'captures': len(selected), 'business_addresses': present, 'source_read_units': (len(selected) + 1) // 2, 'raw_address_derivation_matches': True,
              'full_company_mastering': False, 'census_provenance_qualified': False,
              'receipts_sha256': hashlib.sha256(receipts).hexdigest(), 'contract_sha256': digest(contract_body),
              'execution_sha256s': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(source_read.__file__), *source_read.runtime_files()]},
              'elapsed_seconds': round(time.monotonic() - started, 3), 'evidence': evidence}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'evidence'}))


if __name__ == '__main__':
    main()
