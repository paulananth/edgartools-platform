"""An independently pinned XML header cannot contradict its exact input context."""
import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers import source_read
from tests.engine.test_gleif_reading_contracts import MEMBERS, archive, bound_task, configured


def count_bound_rules(member):
    rules = configured(member, 'xml')
    header = rules['read']['stream']['header_read']
    header['assertions'].append({'test':{'equal':{
        'left':{'integer':{'path':'RecordCount.$'}},
        'right':{'context':{'name':'publication_count'}}}},
        'reason':'Header count must equal the input-bound publication count'})
    return rules


@pytest.mark.parametrize('member', MEMBERS)
def test_equal_header_and_input_context_complete_and_verify(tmp_path, member):
    rules, store = count_bound_rules(member), Artifacts()
    task = bound_task(tmp_path, store, archive(rules, member, 'xml'), rules)
    receipt = source_read.execute(task, store)
    assert source_read.verify({**task, 'candidate':receipt}, store) == ({'source.output':True}, [])


@pytest.mark.parametrize('member', MEMBERS)
def test_header_reference_four_context_three_actual_three_refuses(tmp_path, member):
    rules, store = count_bound_rules(member), Artifacts()
    header = rules['read']['stream']['header_read']
    header['references']['record_counts'] = {'4':{'valid':True}}
    body = archive(rules, member, 'xml', header_changes={'RecordCount':'4'})
    task = bound_task(tmp_path, store, body, rules, count=3)
    with pytest.raises(SourceRejected, match='input-bound publication count'):
        source_read.execute(task, store)
    assert not (tmp_path / 'reading.json').exists()
    assert not (tmp_path / 'reading.json.parts').exists()
