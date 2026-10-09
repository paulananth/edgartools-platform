"""Offline, bounded Company recent-form collection against retained readers.

Actual source.read workers/verifiers read receipt-pinned captures in pairs;
source.combine collects across up to eight such readings. This qualifies
recent-form grouping, not paginated history or complete Company mastering.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import digest
from tests.support.retired_submission_loaders.bronze_submission_extractors import stage_recent_filing_loader
from tests.support.retired_company_preparation import _filed_forms
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_combine, source_read


def combination(names):
    return {"execution": {"profile": "source.combine"}, "combine": {"max_rows": 100000,
        "groups": {"forms": {"source": names, "table": "filings", "key": "cik", "value": "form", "mode": "collect",
                             "order_by": ["form"], "distinct": True, "skip_null_values": True,
                             "checks": {"sync_run_id": "qualification"}, "where": {}}},
        "tables": {"companies": {"source": names, "table": "companies", "checks": {}, "where": {},
            "joins": {"forms": {"group": "forms", "key": "cik", "on_missing": "empty", "replace": False}}}}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--filing-contract', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error('--limit must be 1..1000')
    started = time.monotonic()
    root = args.capture.resolve()
    receipt_bytes = (root / 'receipts.jsonl').read_bytes()
    refs = [json.loads(line) for line in receipt_bytes.splitlines() if line.strip()]
    refs = [ref for ref in refs if '/submissions/' in ref['key'] and '/main/' in ref['key']]
    refs.sort(key=lambda ref: hashlib.sha256(ref['key'].encode()).hexdigest())
    selected = refs[:args.limit]
    if len(selected) != args.limit or len({ref['key'] for ref in selected}) != args.limit:
        raise ValueError('Need requested distinct receipt-pinned captures')
    store = Artifacts()
    spec = files.load(args.filing_contract)
    spec['read']['tables']['companies'] = {'each': '.', 'columns': {'cik': {'context': {'name': 'cik'}}}}
    contracts = set()
    evidence, read_units, combine_units, total = [], 0, 0, 0
    with tempfile.TemporaryDirectory(prefix='codex-combined-forms-') as folder:
        scratch = Path(folder)
        contract = store.put(scratch.as_uri(), spec)
        for start in range(0, len(selected), 16):
            chunk = selected[start:start + 16]
            readings, expected_rows, identities = [], [], []
            for pair_start in range(0, len(chunk), 2):
                entries = []
                for ref in chunk[pair_start:pair_start + 2]:
                    path = (root / 'bronze' / ref['key'].removeprefix('warehouse/bronze/')).resolve()
                    if not path.is_relative_to(root / 'bronze'):
                        raise ValueError('Receipt key escapes capture root')
                    input_ref = {'uri': path.as_uri(), 'sha256': ref['sha256']}
                    payload = json.loads(store.verified(input_ref, max_bytes=32 * 1024**2))
                    context = {'cik': int(payload['cik']), 'sync_run_id': 'qualification', 'raw_object_id': ref['sha256'],
                               'load_mode': 'default', 'recent_limit': None}
                    rows = stage_recent_filing_loader(payload, **context)
                    expected_rows.extend({'cik': row['cik'], 'form': row['form'], 'last_sync_run_id': context['sync_run_id']} for row in rows)
                    total += len(rows)
                    identities.append((ref, context['cik']))
                    bound = store.put(scratch.as_uri(), {'version': 1, 'input': input_ref, 'values': context})
                    entries.append({'input': input_ref, 'context': bound})
                manifest = store.put(scratch.as_uri(), {'version': 2, 'contract': contract, 'artifacts': entries})
                work = {'input': manifest, 'output': (scratch / f'reading-{read_units}.json').as_uri(), 'checks': ['source.output']}
                result = source_read.execute(work, store)
                assert source_read.verify({**work, 'candidate': result}, store) == ({'source.output': True}, [])
                readings.append(result)
                read_units += 1
            parquet = scratch / f'forms-{combine_units}.parquet'
            schema = pa.schema([('cik', pa.int64()), ('form', pa.string()), ('last_sync_run_id', pa.string())])
            pq.write_table(pa.Table.from_pylist(expected_rows, schema=schema), parquet)
            expected = _filed_forms({'run_id': 'qualification'}, pq.ParquetFile(parquet))
            named = {f"reading{n}": ref for n, ref in enumerate(readings)}
            combine = combination(list(named))
            combine_contract = store.put(scratch.as_uri(), combine)
            contracts.add(combine_contract["sha256"])
            manifest = store.put(scratch.as_uri(), {"version": 1, "contract": combine_contract, "readings": named})
            work = {"input": manifest, "output": (scratch / f'combined-{combine_units}.json').as_uri(), 'checks': ['source.combined'], 'keys': {}}
            result = source_combine.execute(work, store)
            assert source_combine.verify({**work, 'candidate': result}, store) == ({'source.combined': True}, [])
            rows = store.json(result)['artifacts'][0]['tables']['companies']
            actual = {row['cik']: row['forms'] for row in rows}
            if len(rows) != len(identities) or len(actual) != len(identities):
                raise ValueError('Repeated CIKs require explicit publication separation')
            for ref, cik in identities:
                if actual[cik] != expected.get(cik, []):
                    raise ValueError(f"Recent Company forms differ: {ref['key']}")
                evidence.append({'key': ref['key'], 'input_sha256': ref['sha256'], 'cik': cik,
                                 'forms_sha256': digest(actual[cik]), 'distinct_forms': len(actual[cik])})
            combine_units += 1
    result = {'captures': len(selected), 'recent_filing_rows': total, 'source_read_units': read_units, 'source_combine_units': combine_units,
              'recent_forms_match': True, 'pagination_qualified': False, 'full_company_mastering': False,
              'receipts_sha256': hashlib.sha256(receipt_bytes).hexdigest(), 'read_contract_sha256': digest(spec),
              'combine_contract_sha256s': sorted(contracts), 'elapsed_seconds': round(time.monotonic() - started, 3), 'evidence': evidence}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'evidence'}))


if __name__ == '__main__':
    main()
