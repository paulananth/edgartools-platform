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
