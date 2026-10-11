"""Offline migration oracle from the pinned pre-port commit; no runtime fallback."""
import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import tempfile

from edgar_warehouse.control_contract import canonical
from edgar_warehouse.rules.source_engine import combine_tables
from tests.engine.test_source_combine import group, table, join

BASELINE = 'cd27767713ba651b6531b3ebb6ba61192d105905'

def baseline():
    body = subprocess.run(['git', 'show', f'{BASELINE}:edgar_warehouse/workers/source_combine.py'], check=True, capture_output=True).stdout
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'baseline.py'
        path.write_bytes(body)
        spec = importlib.util.spec_from_file_location('edgar_warehouse.workers._combination_oracle', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def expected(module, config, inputs):
    groups = {name: module._group(spec, inputs, config['max_rows']) for name, spec in config['groups'].items()}
    result, count = {}, 0
    for name, spec in config['tables'].items():
        output_rows = []
        for row in module._rows(spec, inputs):
            output = dict(row)
            for field, rule in sorted(spec['joins'].items(), key=lambda item: len(item[1].get('path', [item[0]]))):
                if 'path' not in rule and rule['on_missing'] != 'skip' and field in output and not rule['replace']:
                    raise ValueError(f'Join would overwrite column {field}; declare replace explicitly')
                key = module._key(module._column(row, rule['key']))
                values = groups[rule['group']]
                if key not in values:
                    if rule['on_missing'] == 'error':
                        raise ValueError(f'No combination group match for {field}')
                    if rule['on_missing'] == 'skip':
                        continue
                    value = [] if config['groups'][rule['group']]['mode'] in module.COLLECTION_MODES else None
                else:
                    value = values[key]
                module._join_field(output, field, rule, value)
            for column in spec.get('drop', []):
                if column not in output:
                    raise ValueError(f'Drop names missing output column {column}')
                del output[column]
            output_rows.append(output)
            count += 1
            if count > config['max_rows']:
                raise ValueError('Combination exceeds output row budget')
        result[name] = output_rows
    return result


def outcome(call):
    try:
        return ['result', canonical(call())]
    except Exception as error:
        return ['error', type(error).__name__, str(error)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    old = baseline()
    rng = random.Random(911920)
    corpus = [None, False, True, 0, 0.0, -0.0, 1, 1.0, 10**80, -(10**80), '', '雪', '\ud800', 'a\udfff', {'\ud800':'escaped'}, [], {}, ['x'], {'b': 0, 'a': 1}]
    errors = 0
    for case in range(1500):
        mode = rng.choice(['collect', 'collect_flat', 'first', 'last', 'one'])
        rows = [{'id': rng.choice([0, 1, '1', '\ud800', None, 10**80]), 'value': deepcopy(rng.choice(corpus)),
                 'rank': rng.randrange(4), 'fence': 'ok'} for _ in range(rng.randrange(1, 20))]
        if mode == 'collect_flat':
            for row in rows:
                row['value'] = [deepcopy(rng.choice(corpus)) for _ in range(rng.randrange(5))]
        spec = group('raw', 'rows', 'id', 'value', mode=mode, distinct=(mode in ['collect', 'collect_flat'] and rng.choice([False, True])),
                     order_by=rng.choice([[], ['rank']]), checks={'fence':'ok'})
        spec['skip_null_values'] = rng.choice([False, True])
        if mode in ['collect', 'collect_flat']:
            spec['skip_empty_text'] = rng.choice([False, True]); spec['sort_values'] = rng.choice([False, True])
        chosen = join('v', 'id', missing=rng.choice(['empty', 'skip', 'error']))
        config = {'max_rows': rng.choice([10,100]), 'groups': {'v': spec}, 'tables': {'out': table('raw', 'rows', {'chosen': chosen})}}
        if case % 7 == 0:
            rows[0]['id'] = True
        if case % 11 == 0:
            rows[-1].pop('fence')
        if case % 13 == 0:
            rows[0]['chosen'] = 'existing'
        if case % 17 == 0:
            chosen['path'] = ['object', 'chosen']; rows[0]['object'] = rng.choice([{}, None, 1, []])
        if case % 19 == 0:
            config['tables']['out']['drop'] = [rng.choice(['rank', 'missing'])]
        inputs = {'raw': {'artifacts': [{'tables': {'rows': rows}}]}}
        before = canonical(inputs)
        a = outcome(lambda: expected(old, config, inputs))
        b = outcome(lambda: combine_tables(config, inputs, canonical))
        assert a == b, (case, config, inputs, a, b)
        assert canonical(inputs) == before, case
        errors += a[0] == 'error'
    result = {'baseline': BASELINE, 'seed': 911920, 'cases': 1500, 'matching_failures': errors,
              'exact_values_types_order_and_errors': True, 'inputs_unchanged': True}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
