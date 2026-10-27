"""Stored observed starts are reconciled after the existing temporal calculation."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from edgar_warehouse.mdm.clean import relationships
from edgar_warehouse.mdm.clean.store import digest
from tests.mdm.test_clean_parent_history import TYPES, PARENT, ULTIMATE, AS_OF, Y2020, Y2022, Y2024


def calculate(links, stored, types=TYPES, entities=None):
    names = {n for child, parent, _, _ in links for n in (child, parent)}
    claims = {f'r{i}': {'assertion_id': f'a{i}', 'source_meta': {'effective_at': Y2024},
                       'relationships': [{'type': kind, 'source_subject': child, 'target_subject': parent,
                                          'scope': '', **period}]}
              for i, (child, parent, kind, period) in enumerate(links)}
    state = SimpleNamespace(bindings={n: n for n in names}, canonical={n: n for n in names})
    entities = entities or {n: {'kind': 'company', 'status': 'accepted', 'profiles': []} for n in names}
    return relationships.project(claims, state, entities, AS_OF, types=types, stored=stored)


def history(kind=PARENT, child='A', parent='B', **period):
    key = digest([kind, child, parent, ''])
    return {key: {'relationship_id': key, 'periods': [
        {'valid_from': Y2020, 'valid_from_basis': 'observed', **period}]}}


def direct(edges):
    return [e for e in edges if not e['derived']]


def test_stored_start_changes_direct_period_after_ultimate_history_is_calculated():
    old = history()
    before = deepcopy(old)
    edges, reviews = calculate([('A', 'B', PARENT, {})], old)
    assert not reviews
    assert direct(edges)[0]['periods'] == [{'valid_from': Y2020, 'valid_from_basis': 'observed'}]
    derived = [e for e in edges if e['derived']]
    assert [(p['valid_from'], p['valid_to']) for p in derived[0]['periods']] == [(Y2024, None)]
    assert old == before


@pytest.mark.parametrize('kind', ['overlap', 'cycle'])
def test_restored_start_does_not_rerun_hierarchy_checks(kind):
    earlier = ('A', 'C', PARENT, {'valid_from': Y2020, 'valid_to': Y2022}) if kind == 'overlap' else (
        'B', 'A', PARENT, {'valid_from': Y2020, 'valid_to': Y2022})
    edges, reviews = calculate([('A', 'B', PARENT, {}), earlier], history())
    assert reviews == []
    assert len(direct(edges)) == 2
    assert next(e for e in direct(edges) if e['target_id'] == 'B')['periods'][0]['valid_from'] == Y2020


def test_profile_eligibility_is_checked_before_stored_start_is_restored():
    types = {**TYPES, 'PROFILE_LINK': {'from': ['company'], 'to': ['company'], 'to_profile': 'adviser'}}
    entities = {'A': {'kind': 'company', 'status': 'accepted', 'profiles': []},
                'B': {'kind': 'company', 'status': 'accepted', 'profiles': [
                    {'role': 'adviser', 'valid_from': Y2022}]}}
    edges, reviews = calculate([('A', 'B', 'PROFILE_LINK', {})], history('PROFILE_LINK'), types, entities)
    assert reviews == []
    assert edges[0]['periods'] == [{'valid_from': Y2020, 'valid_from_basis': 'observed'}]


def test_stored_history_does_not_resurrect_link_removed_by_succession():
    edges, reviews = calculate([('A', 'B', PARENT, {}),
                               ('A', 'S', 'SUCCESSOR_ENTITY', {'valid_from': Y2022})], history())
    assert [e['type'] for e in edges] == ['SUCCESSOR_ENTITY']
    assert [r['reason'] for r in reviews] == ['parent_link_after_succession']


def test_stated_start_is_not_replaced_by_stored_observation():
    edges, _ = calculate([('A', 'B', PARENT, {'valid_from': Y2024})], history())
    assert direct(edges)[0]['periods'] == [{'valid_from': Y2024, 'valid_from_basis': 'stated'}]


# A type that keeps its start (ticket 113; operator, 2026-10-19: "if issued by already exist do not
# overight"; a backfill: "Keep the earlier date"): its earliest start wins, whatever its basis.
KEEPS = {**TYPES, 'ISSUED_BY': {'from': ['company'], 'to': ['company'], 'keeps_start': True}}
Y2021 = '2021-06-30T00:00:00+00:00'


def stated_history(start, kind='ISSUED_BY'):
    key = digest([kind, 'A', 'B', ''])
    return {key: {'relationship_id': key, 'periods': [{'valid_from': start, 'valid_from_basis': 'stated'}]}}


def test_a_link_that_keeps_its_start_is_not_moved_forward_by_a_later_stated_one():
    edges, reviews = calculate([('A', 'B', 'ISSUED_BY', {'valid_from': Y2024})], stated_history(Y2020), KEEPS)
    assert not reviews and edges[0]['periods'] == [{'valid_from': Y2020, 'valid_from_basis': 'stated'}]


def test_a_backfilled_earlier_start_moves_it_back():
    edges, _ = calculate([('A', 'B', 'ISSUED_BY', {'valid_from': Y2020})], stated_history(Y2024), KEEPS)
    assert edges[0]['periods'] == [{'valid_from': Y2020, 'valid_from_basis': 'stated'}]


def test_an_observed_start_already_held_is_kept_against_a_later_stated_one():
    edges, _ = calculate([('A', 'B', 'ISSUED_BY', {'valid_from': Y2024})], history('ISSUED_BY'), KEEPS)
    assert edges[0]['periods'] == [{'valid_from': Y2020, 'valid_from_basis': 'observed'}]


def test_two_records_in_one_run_give_one_period_at_the_earlier_start():
    edges, _ = calculate([('A', 'B', 'ISSUED_BY', {'valid_from': Y2024}),
                          ('A', 'B', 'ISSUED_BY', {'valid_from': Y2021})], None, KEEPS)
    assert edges[0]['periods'] == [{'valid_from': Y2021, 'valid_from_basis': 'stated'}]


def test_a_type_without_it_still_takes_a_later_stated_start():
    types = {**TYPES, 'ISSUED_BY': {'from': ['company'], 'to': ['company']}}
    edges, _ = calculate([('A', 'B', 'ISSUED_BY', {'valid_from': Y2024})], stated_history(Y2020), types)
    assert edges[0]['periods'] == [{'valid_from': Y2024, 'valid_from_basis': 'stated'}]


@pytest.mark.parametrize('spec, words', [
    ({'keeps_start': 'yes'}, 'rules it cannot run'),
    ({'keeps_start': True, 'hierarchy': True, 'cycles': 'invalid'}, 'keeps_start is true'),
])
def test_keeps_start_is_true_and_never_on_a_hierarchy(spec, words):
    from edgar_warehouse.mdm.clean.store import Conflict

    with pytest.raises(Conflict, match=words):
        relationships.check_types({'X': {'from': ['company'], 'to': ['company'], **spec}})
