"""Exact retained keys from shipped recipes, without custom callbacks."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from edgar_warehouse.mdm.clean.names import legal_form_key, sec_legal_form_key
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.rules import files

@pytest.fixture(autouse=True)
def no_custom_steps(monkeypatch):
    monkeypatch.setattr('edgar_warehouse.rules.source_engine.STEPS', {})


ROOT = Path(__file__).resolve().parents[2]
SAMPLES = [None, '', False, 123, ['THE Inc'], {'name': 'A&B'},
           'Électricité Holdings Corporation /DE/', 'THE A&B L.L.C.',
           'Wayfair Inc.', 'WAYFAIR LLC', 'COUSINS PROPERTIES INC', 'COUSINS PROPERTIES LP',
           'International Company Limited', 'A L L P', 'A L P', 'THE THE INC',
           'The A.G. /D E/', 'A/B INTERNATIONAL /123456/', 'A/B /1234567/',
           '\u001cThe A & B\u001f/DE/\u001e', 'Kelvin 𝑨 ﬁrm ＬＬＣ',
           'Straße Company', 'İ Company', 'ﬃ Company', 'A\u034f B',
           'A  Holdings Holdings', 'A INC /DE/\n', 'A INC /DE/\u0085',
           'A NV /DE//', 'N.V. & S.A. & B.V. & S.E. & P.L.C.']


def contract(source):
    return files.load(ROOT / f'rules/sources/{source}/name-key.yaml')


def keys(config, samples):
    reading = SourceEngine(config).read(json.dumps({'names': [{'name': s} for s in samples]}).encode())
    assert not reading.deferred
    return [row['key'] for row in reading.tables['names']]


@pytest.mark.parametrize('source,oracle', [('sec.submissions.company', sec_legal_form_key), ('gleif', legal_form_key)])
def test_shipped_recipe_matches_retained_normalizer(source, oracle):
    assert keys(contract(source), SAMPLES) == [oracle(s) for s in SAMPLES]


def test_missing_name_uses_empty_key_and_legal_forms_remain_distinct():
    config = contract('sec.submissions.company')
    reading = SourceEngine(config).read(b'{"names":[{}]}')
    assert reading.tables['names'][0]['key'] == ''
    values = keys(config, ['Wayfair Inc.', 'Wayfair LLC', 'COUSINS PROPERTIES INC', 'COUSINS PROPERTIES LP'])
    assert len(set(values)) == 4


@pytest.mark.parametrize('operation,sample', [('unicode','𝑨 Company'), ('strip_combining','Électricité Company'),
                                            ('remove_prefix','THE COMPANY'), ('replace','A&B Company')])
def test_deliberate_missing_operation_changes_required_key(operation, sample):
    config = deepcopy(contract('sec.submissions.company'))
    ops = config['read']['tables']['names']['columns']['key']['text']['transforms']
    # Keep only the first replace fault: remove ampersand handling, not aliases.
    index = next(i for i, op in enumerate(ops) if operation in op)
    del ops[index]
    assert keys(config, [sample]) != [sec_legal_form_key(sample)]


def test_deliberate_state_suffix_and_legal_form_alias_faults_are_observable():
    config = deepcopy(contract('sec.submissions.company'))
    ops = config['read']['tables']['names']['columns']['key']['text']['transforms']
    del ops[1]
    assert keys(config, ['A INC /DE/']) != ['A INC']
    config = deepcopy(contract('sec.submissions.company'))
    ops = config['read']['tables']['names']['columns']['key']['text']['transforms']
    ops[:] = [op for op in ops if op.get('replace', {}).get('from') != ' CORPORATION ']
    assert keys(config, ['A Corporation']) != ['A CORP']


def test_python_facade_refuses_regex_and_output_growth():
    config = deepcopy(contract('sec.submissions.company'))
    text = config['read']['tables']['names']['columns']['key']['text']
    text['transforms'] = [{'regex_replace': {'pattern': '(', 'with': ''}}]
    with pytest.raises(SourceRejected, match='contract'):
        SourceEngine(config)
    text['transforms'] = [{'replace': {'from': 'A', 'to': 'AA'}}]
    with pytest.raises(SourceRejected, match='text_transform_limit'):
        keys(config, ['A' * (1 << 20)])
