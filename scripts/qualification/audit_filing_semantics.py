"""Bounded offline refusal audit; retained-reader comparison, never activation.

Runs a fixed 450-case finite JSON anchor/field/first-N matrix. This is narrower
than complete source equivalence; reports both rejected as a matching refusal
decision without claiming matching exception classes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from itertools import product
from pathlib import Path

from edgar_warehouse.loaders.bronze_submission_extractors import stage_recent_filing_loader
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected

CONTEXT = {'cik': 320193, 'sync_run_id': 'qualification', 'raw_object_id': 'captured',
           'load_mode': 'default', 'recent_limit': None}


def compare(engine: SourceEngine, payload: dict, limit: int | None) -> dict:
    try:
        rows = stage_recent_filing_loader(payload, 320193, 'qualification', 'captured', 'default', limit)
        retained = {'rows': [{key: value.isoformat() if hasattr(value, 'isoformat') else value
                              for key, value in row.items()} for row in rows]}
    except (TypeError, KeyError, ValueError) as error:
        retained = {'error': type(error).__name__}
    try:
        configured = {'rows': engine.read(json.dumps(payload).encode(),
                         context={**CONTEXT, 'recent_limit': limit}).tables['filings']}
    except SourceRejected as error:
        configured = {'error': error.code}
    same = retained == configured or ('error' in retained and 'error' in configured)
    return {'payload': payload, 'recent_limit': limit, 'retained': retained,
            'configured': configured, 'same_acceptance_and_rows': same}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    engine = SourceEngine(files.load(args.contract))
    anchors = [[], ['a'], ['a', 'b'], 'ab', {}, {'x': 'a'}, None, True, 1]
    fields = [[], ['4'], [True], [{'x': 1}], None, True, 1, {}, {'x': 1}, 'é🦀']
    results = [compare(engine, {'filings': {'recent': {'accessionNumber': anchor, 'form': field}}}, limit)
               for anchor, field, limit in product(anchors, fields, [None, -1, 0, 1, 2])]
    differences = [case for case in results if not case['same_acceptance_and_rows']]
    summary = {
        'scope': 'Finite JSON anchor/field/first-N acceptance matrix; both refusals are counted separately from exact exception identity. Not complete source equivalence.',
        'cases': len(results), 'matched': len(results) - len(differences), 'differences': differences,
        'contract_sha256': hashlib.sha256(args.contract.read_bytes()).hexdigest(),
        'matrix_sha256': hashlib.sha256(json.dumps(results, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({key: summary[key] for key in ('cases', 'matched', 'matrix_sha256')}))


if __name__ == '__main__':
    main()
