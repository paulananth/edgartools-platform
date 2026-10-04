"""Offline, receipt-bound raw Person and Company extraction equivalence.

This compares complete Person records and governed assertion/deferral bodies,
not only field equality. Company compares its 14 raw landing columns; joins,
addresses, pagination and full Company mastering are separate gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine
from edgar_warehouse.loaders.bronze_submission_extractors import stage_company_loader
from edgar_warehouse.mdm.clean.adapters import normalize, UnsupportedRecord
from edgar_warehouse.mdm.clean.store import canonical, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--company-contract', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error('--limit must be 1..1000')
    root = args.capture.resolve()
    receipt_bytes = (root / 'receipts.jsonl').read_bytes()
    receipts = [json.loads(line) for line in receipt_bytes.splitlines() if line.strip()]
    receipts = [r for r in receipts if '/submissions/' in r['key'] and '/main/' in r['key']]
    receipts.sort(key=lambda r: hashlib.sha256(r['key'].encode()).hexdigest())
    selected = receipts[:args.limit]
    if len(selected) != args.limit or len({r['key'] for r in selected}) != args.limit:
        raise ValueError('Need the requested distinct receipt-pinned submissions')
    person_contract = files.source('sec.submissions.person')
    person = SourceEngine(person_contract)
    company_contract = files.load(args.company_contract)
    company = SourceEngine(company_contract)
    dataset = files.mdm_contract('sec.submissions.person', 'sec.submissions.person.v1')
    policy = files.policy()
    outcomes = Counter()
    evidence = []
    for ref in selected:
        path = (root / 'bronze' / ref['key'].removeprefix('warehouse/bronze/')).resolve()
        if not path.is_relative_to(root / 'bronze'):
            raise ValueError('Receipt key escapes capture root')
        with path.open('rb') as stream:
            raw = stream.read(32 * 1024**2 + 1)
        if len(raw) > 32 * 1024**2 or hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError(f"Invalid capture bytes: {ref['key']}")
        payload = json.loads(raw)
        reading = person.read(raw)
        actual = reading.tables['submissions'][0]['record']
        if reading.deferred or canonical(actual) != canonical(payload):
            raise ValueError(f"Complete raw Person record differs: {ref['key']}")
        publication = {'publication_key': ref['key'], 'revision': 1, 'artifact_sha256': ref['sha256'], 'member': 'submissions.json'}
        def outcome(row):
            try:
                return {'assertion': normalize(row, source_code='sec.submissions.person.v1', contract=dataset,
                                               policy=policy, publication=publication)}
            except UnsupportedRecord as error:
                return {'deferred': error.reason, 'detail': error.detail, 'probable_kind': error.probable_kind}
        expected = outcome(payload)
        actual_outcome = outcome(actual)
        if canonical(actual_outcome) != canonical(expected):
            raise ValueError(f"Person assertion/ID/deferral differs: {ref['key']}")
        label = expected.get('deferred', 'assertion')
        outcomes[label] += 1
        context = {'cik': int(payload['cik']), 'sync_run_id': 'qualification', 'raw_object_id': ref['sha256'], 'load_mode': 'default'}
        old = stage_company_loader(payload, **context)
        new = company.read(raw, context=context)
        if new.deferred or canonical(new.tables['company']) != canonical(old):
            raise ValueError(f"Raw Company extraction differs: {ref['key']}")
        evidence.append({'key': ref['key'], 'input_sha256': ref['sha256'], 'raw_record_sha256': digest(actual),
                         'company_rows_sha256': digest(old), 'person_outcome': label, 'person_outcome_sha256': digest(actual_outcome)})
    result = {'captures': len(selected), 'complete_person_records': True, 'person_assertions_ids_deferrals': True,
              'company_columns': list(company_contract['read']['tables']['company']['columns']),
              'full_company_mastering': False, 'person_outcomes': dict(outcomes),
              'receipts_sha256': hashlib.sha256(receipt_bytes).hexdigest(),
              'person_read_sha256': digest(person_contract['read']), 'person_dataset_sha256': digest(dataset),
              'policy_sha256': digest(policy), 'company_contract_sha256': hashlib.sha256(args.company_contract.read_bytes()).hexdigest(),
              'evidence': evidence}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'evidence'}))


if __name__ == '__main__':
    main()
