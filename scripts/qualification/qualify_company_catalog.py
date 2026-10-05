"""Offline pinned catalog row parity and Company ticker joins through receipts."""
from __future__ import annotations
import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from tests.support.ticker_catalog_oracle import parse_rows
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare
from scripts.qualification.qualify_company_main import require_tables


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--catalog-receipt', type=Path)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    catalog = args.catalog.resolve()
    if catalog.stat().st_size > 32 * 1024**2: raise ValueError('Catalog exceeds 32 MiB')
    raw = catalog.read_bytes()
    payload = json.loads(raw)
    rows = parse_rows(payload)
    matrix_layout = isinstance(payload.get('fields'), list) and isinstance(payload.get('data'), list)
    receipt = None
    if args.catalog_receipt is not None:
        receipt_path = args.catalog_receipt.resolve()
        if receipt_path.stat().st_size > 1024**2: raise ValueError('Catalog receipt exceeds budget')
        document = json.loads(receipt_path.read_bytes())
        members = [r for r in document['objects'] if (receipt_path.parent / r['path']).resolve() == catalog]
        if len(members) != 1: raise ValueError('Need one exact catalog receipt')
        receipt = members[0]
        if not receipt.get('version_id') or not receipt.get('bucket') or receipt['size'] != len(raw) or receipt['sha256'] != hashlib.sha256(raw).hexdigest(): raise ValueError('Catalog receipt differs')
    context = {'sync_run_id': 'catalog-qualification', 'source_name': 'company_tickers_exchange' if matrix_layout else 'company_tickers',
               'last_synced_at': '2026-10-05T00:00:00Z'}
    expected = [{**row, 'source_rank': rank, 'source_name': context['source_name'],
                 'last_sync_run_id': context['sync_run_id'], 'last_synced_at': context['last_synced_at']}
                for rank, row in enumerate(rows, 1)]
    tickers = {}
    for row in rows:
        if not row['ticker']: continue
        if row['ticker'] not in tickers.setdefault(row['cik'], []): tickers[row['cik']].append(row['ticker'])
    captures = args.captures.resolve()
    manifest_bytes = (captures / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    mains = [r for r in manifest['objects'] if r['kind'] == 'main']
    if not 1 <= len(mains) <= 10: raise ValueError('Need 1..10 Company captures')
    store = Artifacts()
    contracts = {'catalog': files.load(Path('rules/sources/sec.submissions.company/catalog.yaml')),
                 'main': files.source('sec.submissions.company')}
    def read(root, name, contract, body, values):
        ref = store.put_bytes((root / (name + '.json')).as_uri(), body)
        bound = store.put(root.as_uri(), {'version': 1, 'input': ref, 'values': values})
        saved = store.put(root.as_uri(), contract)
        request = store.put(root.as_uri(), {'version': 2, 'contract': saved, 'artifacts': [{'input': ref, 'context': bound}]})
        work = {'input': request, 'output': (root / (name + '-reading.json')).as_uri(), 'checks': ['source.output']}
        result = source_read.execute(work, store)
        if source_read.verify({**work, 'candidate': result}, store) != ({'source.output': True}, []): raise ValueError('Read verification failed')
        return result
    publications = []
    with tempfile.TemporaryDirectory(prefix='company-catalog-qualification-') as temporary:
        root = Path(temporary)
        catalog_read = read(root, 'catalog', contracts['catalog'], raw, context)
        require_tables(store.json(catalog_read)['artifacts'][0]['tables']['tickers'], expected)
        for index, capture in enumerate(mains):
            path = (captures / capture['path']).resolve()
            if not path.is_relative_to(captures) or path.stat().st_size > 32 * 1024**2: raise ValueError('Invalid Company path/size')
            if not capture.get('version_id') or capture.get('bucket') != manifest['bucket']: raise ValueError('Missing capture bucket/version')
            body = path.read_bytes()
            if len(body) != capture['size']: raise ValueError('Company capture size differs')
            if hashlib.sha256(body).hexdigest() != capture['sha256']: raise ValueError('Company bytes changed')
            cik = capture['cik']
            if int(json.loads(body)['cik']) != cik: raise ValueError('Company CIK differs')
            values = {'cik': cik, 'sync_run_id': 'company-qualification', 'raw_object_id': capture['sha256'],
                      'load_mode': 'default', 'recent_limit': 0, 'last_synced_at': context['last_synced_at']}
            main_read = read(root, f'main-{index}', contracts['main'], body, values)
            combine = {'execution': {'profile': 'source.combine'}, 'combine': {'max_rows': 100000,
                'groups': {'tickers': {'source': 'catalog', 'table': 'tickers', 'key': 'cik', 'value': 'ticker',
                    'mode': 'collect', 'order_by': ['source_rank'], 'distinct': True, 'skip_null_values': True, 'skip_empty_text': True,
                    'checks': {'last_sync_run_id': context['sync_run_id']}, 'where': {}}},
                'tables': {'company': {'source': 'main', 'table': 'company', 'checks': {'last_sync_run_id': values['sync_run_id']},
                    'where': {}, 'joins': {'tickers': {'group': 'tickers', 'key': 'cik', 'on_missing': 'empty', 'replace': False}}}}}}
            request = store.put(root.as_uri(), {'version': 1, 'contract': store.put(root.as_uri(), combine),
                                               'readings': {'main': main_read, 'catalog': catalog_read}})
            work = {'input': request, 'output': (root / f'combined-{index}.json').as_uri(), 'checks': ['source.combined']}
            combined = source_combine.execute(work, store)
            if source_combine.verify({**work, 'candidate': combined}, store) != ({'source.combined': True}, []): raise ValueError('Combination verification failed')
            found = store.json(combined)['artifacts'][0]['tables']['company'][0]
            require_tables(found['tickers'], tickers.get(cik, []))
            prepared_work = {'input': combined, 'output': (root / f'prepared-{index}' / 'manifest.json').as_uri(),
                'checks': ['mdm.prepared'], 'keys': {'table': 'company', 'dataset': 'sec.submissions.company.v1', 'policy': '0' * 64,
                    'consumer': 'trial', 'batch_id': str(index), 'as_of': context['last_synced_at']}}
            prepared = mdm_prepare.execute(prepared_work, store)
            if mdm_prepare.verify({**prepared_work, 'candidate': prepared}, store) != ({'mdm.prepared': True}, []): raise ValueError('Prepare verification failed')
            publications.append({'cik': cik, 'tickers': found['tickers'], 'main_sha256': capture['sha256'],
                                 'combined_sha256': combined['sha256'], 'prepared_sha256': prepared['sha256']})
    report = {'catalog_rows': len(rows), 'catalog_sha256': hashlib.sha256(raw).hexdigest(),
        'capture_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(), 'companies': len(mains),
        'exact_typed_catalog_rows': True, 'ranked_distinct_ticker_joins': True,
        'elapsed_seconds': round(time.monotonic() - started, 3), 'publications': publications,
        'execution_sha256s': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [
            *source_read.runtime_files(), Path(source_read.__file__), Path(source_combine.__file__),
            *source_combine.runtime_files(), Path(mdm_prepare.__file__)]},
        'contract_sha256s': {name: hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                            for name, body in contracts.items()},
        'sec_requests': 0, 'producer_provenance_qualified': False, 'full_company_mastering': False,
        'catalog_layout': 'matrix' if matrix_layout else 'dictionary',
        'catalog_receipt': receipt,
        'legacy_dictionary_catalog_qualified': not matrix_layout,
        'universal_malformed_catalog_equivalence': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
