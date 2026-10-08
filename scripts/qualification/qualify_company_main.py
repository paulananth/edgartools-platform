"""Bounded offline configured Company main reading; no full mastering claim."""
from __future__ import annotations
import argparse
import hashlib
import json
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import digest
from tests.support.retired_submission_loaders.bronze_submission_extractors import stage_company_loader, stage_recent_filing_loader, stage_address_loader
from tests.support.retired_company_address import business_address
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read


def _scalar(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f'Unexpected retained scalar: {type(value).__name__}')


def require_tables(actual, expected):
    """Exact JSON values: Python equality conflates booleans and numbers."""
    if digest(actual) != digest(expected):
        raise ValueError('Company main tables differ in values or JSON scalar types')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
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
    store, evidence, filing_count = Artifacts(), [], 0
    contract_body = files.source('sec.submissions.company')
    with tempfile.TemporaryDirectory(prefix='codex-company-main-') as folder:
        scratch = Path(folder)
        contract = store.put(scratch.as_uri(), contract_body)
        for n in range(0, len(selected), 2):
            entries, expected_rows = [], []
            for ref in selected[n:n + 2]:
                path = (root / 'bronze' / ref['key'].removeprefix('warehouse/bronze/')).resolve()
                if not path.is_relative_to(root / 'bronze'):
                    raise ValueError('Receipt key escapes capture root')
                raw = {'uri': path.as_uri(), 'sha256': ref['sha256']}
                payload = json.loads(store.verified(raw, max_bytes=32 * 1024**2))
                context = {'cik': int(payload['cik']), 'sync_run_id': 'qualification', 'raw_object_id': ref['sha256'],
                           'load_mode': 'default', 'recent_limit': None, 'last_synced_at': '2026-10-04T00:00:00Z'}
                company = stage_company_loader(payload, context['cik'], context['sync_run_id'], context['raw_object_id'], context['load_mode'])[0]
                company.update(last_sync_run_id=context['sync_run_id'], last_synced_at=context['last_synced_at'])
                filings = stage_recent_filing_loader(payload, **{k: v for k, v in context.items() if k != 'last_synced_at'})
                address_rows = stage_address_loader(payload, context['cik'], context['sync_run_id'], context['raw_object_id'], context['load_mode'])
                addresses = [{'cik': context['cik'], 'last_sync_run_id': context['sync_run_id'], 'business_address': business_address(row)}
                             for row in address_rows if row['address_type'] == 'business']
                tables = json.loads(json.dumps({'company': [company], 'filings': filings, 'addresses': addresses}, default=_scalar, allow_nan=False))
                bound = store.put(scratch.as_uri(), {'version': 1, 'input': raw, 'values': context})
                entries.append({'input': raw, 'context': bound})
                expected_rows.append((ref, tables))
                filing_count += len(filings)
            manifest = store.put(scratch.as_uri(), {'version': 2, 'contract': contract, 'artifacts': entries})
            work = {'input': manifest, 'output': (scratch / f'reading-{n // 2}.json').as_uri(), 'checks': ['source.output']}
            result = source_read.execute(work, store)
            if source_read.verify({**work, 'candidate': result}, store) != ({'source.output': True}, []):
                raise ValueError('Source worker verification failed')
            read = store.json(result)
            if len(read['artifacts']) != len(entries):
                raise ValueError('Reading artifact count differs from frozen scope')
            for artifact, entry, (ref, tables) in zip(read['artifacts'], entries, expected_rows):
                if artifact['input'] != entry['input'] or artifact.get('context') != entry['context'] or artifact['deferred']:
                    raise ValueError(f"Company main reading differs: {ref['key']}")
                require_tables(artifact['tables'], tables)
                evidence.append({'key': ref['key'], 'input_sha256': ref['sha256'], 'context_sha256': entry['context']['sha256'], 'tables_sha256': digest(tables)})
    result = {'captures': len(selected), 'company_rows': len(selected), 'filing_rows': filing_count, 'source_read_units': (len(selected) + 1) // 2,
              'all_main_tables_match': True, 'full_company_mastering': False, 'census_provenance_qualified': False, 'pagination_qualified': False,
              'receipts_sha256': hashlib.sha256(receipts).hexdigest(), 'contract_sha256': digest(contract_body),
              'execution_sha256s': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(source_read.__file__), *source_read.runtime_files()]},
              'elapsed_seconds': round(time.monotonic() - started, 3), 'evidence': evidence}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'evidence'}))


if __name__ == '__main__':
    main()
