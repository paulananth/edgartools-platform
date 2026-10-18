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
