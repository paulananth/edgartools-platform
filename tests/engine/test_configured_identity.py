"""Native accepted-decision replay uses opaque references for overrides."""
from edgar_warehouse.rules.source_engine import replay_identity


def test_accepted_merge_defaults_to_oldest_identity_and_keeps_bindings():
    ids = [{'id': 'new', 'kind': 'company', 'published': 20},
           {'id': 'old', 'kind': 'company', 'published': 10}]
    base = dict(target=None, subject=None, entity=None, left=None, right=None,
                survivor=None, source=None, expires=None, evidence=True,
                depends=[], entity_present=False)
    decisions = [
        {**base, 'id': 'bind', 'at': 1, 'op': 'bind', 'subject': 's', 'entity': 'new'},
        {**base, 'id': 'merge', 'at': 2, 'op': 'merge', 'left': 'old', 'right': 'new'},
    ]
    state = replay_identity(ids, decisions, 3)
    assert state['canonical'] == {'new': 'old', 'old': 'old'}
    assert state['bindings'] == {'s': 'new'}
    assert state['exclusions'] == []


def test_a_merge_replays_after_the_merges_it_depends_on_at_the_same_time():
    """Two merges one batch makes (ticket 138 part A2a) share their time; the one
    resting on the other is applied after it, whatever their ids sort."""
    ids = [{'id': name, 'kind': 'security', 'published': n} for n, name in enumerate(['a', 'b', 'c'])]
    base = dict(target=None, subject=None, entity=None, left=None, right=None,
                survivor=None, source=None, expires=None, evidence=True,
                depends=[], entity_present=False)
    first = {**base, 'id': 'z-first', 'at': 2, 'op': 'merge', 'left': 'a', 'right': 'b'}
    later = {**base, 'id': 'a-later', 'at': 2, 'op': 'merge', 'left': 'a', 'right': 'c', 'depends': ['z-first']}
    state = replay_identity(ids, [later, first], 3)
    assert state['canonical'] == {'a': 'a', 'b': 'a', 'c': 'a'}
