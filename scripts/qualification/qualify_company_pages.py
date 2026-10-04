"""Offline S3-captured page parity and complete declared-page form combination."""
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
from edgar_warehouse.loaders.bronze_submission_extractors import stage_recent_filing_loader, stage_pagination_filing_loader
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare
from scripts.qualification.qualify_company_main import require_tables


def group(names, table, value, mode='collect'):
    return {'source': names, 'table': table, 'key': 'cik', 'value': value, 'mode': mode, 'order_by': [],
            'distinct': True, 'skip_null_values': True, 'checks': {}, 'where': {}, 'sort_values': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    root = args.capture.resolve()
    raw_manifest = (root / 'manifest.json').read_bytes()
    manifest = json.loads(raw_manifest)
    objects = manifest['objects']
    if not 1 <= len(objects) <= 105 or len({r['key'] for r in objects}) != len(objects):
        raise ValueError('Need a bounded, distinct captured scope of at most 105 objects')
    store = Artifacts()
    contracts = {'main': files.source('sec.submissions.company'),
                 'page': files.load(files.ROOT / 'sources/sec.submissions.company/pagination.yaml')}
    evidence, groups, rows, units = [], {}, 0, 0
    with tempfile.TemporaryDirectory(prefix='codex-company-pages-') as folder:
        scratch = Path(folder)
        saved = {k: store.put(scratch.as_uri(), v) for k, v in contracts.items()}
        for record in objects:
            if record['kind'] not in contracts or not record.get('version_id') or record.get('bucket') != manifest['bucket']:
                raise ValueError('Captured objects need a source kind, bucket and S3 version')
            path = (root / record['path']).resolve()
            if not path.is_relative_to(root): raise ValueError('Capture path escapes its root')
            if record['size'] > 32 * 1024**2: raise ValueError('Captured object exceeds byte budget')
            raw = {'uri': path.as_uri(), 'sha256': record['sha256']}
            data = store.verified(raw, max_bytes=32 * 1024**2)
            if len(data) != record['size']: raise ValueError('Captured size differs')
            payload = json.loads(data)
            key_prefix = f"warehouse/bronze/submissions/sec/cik={record['cik']}/{('main' if record['kind']=='main' else 'pagination')}/"
            if not record['key'].startswith(key_prefix): raise ValueError('Object key differs from declared kind/CIK')
            stamp = record['key'][len(key_prefix):].rsplit('/', 1)[0]
            item = (record, raw, payload)
            groups.setdefault((record['cik'], stamp), {}).setdefault(record['kind'], []).append(item)
        for (cik, stamp), captured in sorted(groups.items()):
            capture_label = f'{cik}-{stamp.replace("/", "-")}'
            if len(captured.get('main', [])) != 1 or not captured.get('page'):
                raise ValueError('Require one main document and pages from its capture date')
            main_record, main_ref, main_payload = captured['main'][0]
            if int(main_payload['cik']) != cik: raise ValueError('Main document CIK differs')
            declared = main_payload['filings']['files']
            names = [d['name'] for d in declared]
            page_items = sorted(captured['page'], key=lambda item: item[0]['key'])
            if len(set(names)) != len(names) or set(names) != {r['key'].rsplit('/', 1)[1] for r, _, _ in page_items}:
                raise ValueError('Captured pages do not exactly cover the main declaration')
            counts = {d['name']: d.get('filingCount') for d in declared}
            context = {'cik': cik, 'sync_run_id': f'qualification-{cik}-{stamp}', 'raw_object_id': main_ref['sha256'], 'load_mode': 'default'}
            expected_forms, page_refs, main_read = set(), [], None
            for kind, items in (('main', captured['main']), ('page', page_items)):
                for offset in range(0, len(items), 2):
                    entries, expected = [], []
                    for record, raw, payload in items[offset:offset + 2]:
                        if kind == 'page' and not isinstance(payload.get('accessionNumber'), list):
                            raise ValueError('A captured raw page must carry an accession array')
                        retained = (stage_pagination_filing_loader({'filings': payload}, **context) if kind == 'page'
                                    else stage_recent_filing_loader(payload, **context))
                        retained = json.loads(json.dumps(retained, default=lambda x: x.isoformat() if isinstance(x, (date, datetime)) else x))
                        if kind == 'page' and counts[record['key'].rsplit('/', 1)[1]] is not None and counts[record['key'].rsplit('/', 1)[1]] != len(retained):
                            raise ValueError('Declared page filing count differs')
                        expected_forms.update(r['form'] for r in retained if r['form'])
                        rows += len(retained)
                        values = context if kind == 'page' else {**context, 'recent_limit': None, 'last_synced_at': '2026-10-04T00:00:00Z'}
                        bound = store.put(scratch.as_uri(), {'version': 1, 'input': raw, 'values': values})
                        entries.append({'input': raw, 'context': bound})
                        expected.append((record, retained))
                    manifest_ref = store.put(scratch.as_uri(), {'version': 2, 'contract': saved[kind], 'artifacts': entries})
                    work = {'input': manifest_ref, 'output': (scratch / f'read-{units}.json').as_uri(), 'checks': ['source.output']}
                    result = source_read.execute(work, store)
                    if source_read.verify({**work, 'candidate': result}, store) != ({'source.output': True}, []): raise ValueError('Read verification failed')
                    units += 1
                    actual = store.json(result)['artifacts']
                    if len(actual) != len(entries): raise ValueError('Reading artifact count differs')
                    for artifact, entry, (record, retained) in zip(actual, entries, expected):
                        if artifact['input'] != entry['input'] or artifact.get('context') != entry['context'] or artifact['deferred']:
                            raise ValueError('Reading receipt/context/deferral differs')
                        require_tables(artifact['tables']['filings'], retained)
                        evidence.append({**record, 'filing_rows': len(retained), 'reading_sha256': result['sha256'], 'context_sha256': entry['context']['sha256']})
                    if kind == 'main': main_read = result
                    else: page_refs.append(result)
            def combine(refs, spec, name):
                body = {'execution': {'profile': 'source.combine'}, 'combine': {'max_rows': 100000, 'groups': {'forms': spec},
                    'tables': {'company': {'source': 'main', 'table': 'company', 'checks': {'last_sync_run_id': context['sync_run_id']},
                    'where': {}, 'joins': {'forms': {'group': 'forms', 'key': 'cik', 'on_missing': 'empty', 'replace': False}}}}}}
                # Every reading has already passed exact capture-context verification above.
                spec['checks'] = ({'sync_run_id': context['sync_run_id']} if spec['table'] == 'filings' else {'last_sync_run_id': context['sync_run_id']})
                ref = store.put(scratch.as_uri(), body)
                source = store.put(scratch.as_uri(), {'version': 1, 'contract': ref, 'readings': refs})
                work = {'input': source, 'output': (scratch / f'{capture_label}-{name}.json').as_uri(), 'checks': ['source.combined']}
                result = source_combine.execute(work, store)
                if source_combine.verify({**work, 'candidate': result}, store) != ({'source.combined': True}, []): raise ValueError('Combination verification failed')
                return result
            parts = []
            for n in range(0, len(page_refs), 7):
                refs = {'main': main_read, **{f'page{k}': r for k, r in enumerate(page_refs[n:n + 7])}}
                parts.append(combine(refs, group(list(refs), 'filings', 'form'), f'part-{n}'))
            if len(parts) > 7: raise ValueError('Sample exceeds final combination scope; partition its publication')
            refs = {'main': main_read, **{f'part{k}': r for k, r in enumerate(parts)}}
            combined = combine(refs, group([name for name in refs if name != 'main'], 'company', 'forms', 'collect_flat'), 'final')
            company = store.json(combined)['artifacts'][0]['tables']['company'][0]
            if company['forms'] != sorted(expected_forms): raise ValueError(f'Full declared-page forms differ: {cik}, actual={company["forms"]!r}, expected={sorted(expected_forms)!r}')
            prepare = {'input': combined, 'output': (scratch / f'mdm-{capture_label}/manifest.json').as_uri(), 'checks': ['mdm.prepared'],
                'keys': {'table': 'company', 'dataset': 'sec.submissions.company.v1', 'policy': '0' * 64, 'consumer': 'qualification',
                         'batch_id': str(cik), 'as_of': '2026-10-04T00:00:00Z'}}
            prepared = mdm_prepare.execute(prepare, store)
            if mdm_prepare.verify({**prepare, 'candidate': prepared}, store) != ({'mdm.prepared': True}, []): raise ValueError('Prepare verification failed')
            batch = store.json(prepared)['batches'][0]
            require_tables(json.loads((scratch / f'mdm-{capture_label}' / batch['input']['path']).read_bytes()), company)
            print(json.dumps({'cik': cik, 'pages': len(page_items), 'form_count': len(company['forms'])}), flush=True)
    summary = {'companies': len(groups), 'pages': sum(r['kind']=='page' for r in objects), 'filing_rows': rows,
        'source_read_units': units, 'captured_pages_qualified': True, 'complete_declared_page_forms_match': True,
        'producer_provenance_qualified': False, 'full_company_mastering': False, 'sec_requests': 0,
        'capture_manifest_sha256': hashlib.sha256(raw_manifest).hexdigest(), 'contract_sha256s': {k: digest(v) for k,v in contracts.items()},
        'execution_sha256s': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(source_read.__file__), *source_read.runtime_files(), Path(source_combine.__file__), Path(mdm_prepare.__file__)]},
        'elapsed_seconds': round(time.monotonic()-started,3), 'evidence': evidence}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='evidence'}))


if __name__=='__main__': main()
