"""Explicit answers retained before retiring the offline implementation oracle.

The input generator calls only the maintained shared engine. No historical code
is loaded. Exact numeric/Unicode outcome encoding preserves the original cases.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random

import pytest

AS_OF = "2026-09-18T00:00:00+00:00"
HELD = json.loads((Path(__file__).parents[1] / "fixtures/clean_mdm/configured-merging-answers.json").read_text())


def encoded(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, default=sorted, separators=(",", ":")).encode()).hexdigest()


def outcome(call):
    try:
        return ('ok', call())
    except (ValueError, KeyError) as error:
        return ('error', type(error).__name__, str(error))


def answers(cases):
    from edgar_warehouse.mdm.clean import identity, survivorship
    from edgar_warehouse.mdm.clean.evidence import assertion, decision
    rng = random.Random(81403)
    values = [True, 1, 1.0, 10**80, -0.0, 1e-7, {'é': [1.0, True]}, ['雪', None]]
    for index in range(cases):
        rows = [assertion(source_code=f's{n % 3}', record_key=str(n), publication_key='p',
                          revision=1, effective_at=rng.choice([None, '2026-09-17T00:00:00Z', '2026-01-01T00:00:00Z']),
                          kind='company', fields={'name': rng.choice(values), 'extra': rng.choice(values)},
                          profiles=[{'role': 'adviser', 'authority': 'SEC', 'registration': '1',
                                     'valid_from': '2026-01-01T00:00:00Z',
                                     'fields': {'aum': rng.choice(values)}}]) for n in range(8)]
        if index % 3 == 0:
            rows[0]['fields']['name'] = {'op': 'clear'}
        claims = survivorship.current_claims(rows, AS_OF, set())
        sources = rng.sample(['s0', 's1', 's2'], rng.randrange(1, 4))
        rule = {'sources': sources, 'clear_sources': rng.sample(sources, rng.randrange(len(sources)+1)),
                'allow_unknown_effective': rng.choice([True, False]), 'max_age_days': rng.choice([None, 1, 30])}
        policy = {'kinds': {'company': {'version': 'v1', 'defaults': rule,
                                      'fields': {'name': {'sources': list(reversed(sources))}}}},
                  'profile_fields': {'adviser': {'aum': rule}}}
        overrides = [dict(subject=rows[0]['subject'], field='name', value=rng.choice(values),
                          decision_id=f'o{n}', reason='reviewed') for n in range(index % 3)]
        args = ('company', [r['subject'] for r in rows], claims, policy, overrides)
        kwargs = dict(as_of=AS_OF, policy_digest='policy', entity_id='entity')
        actual = outcome(lambda: survivorship.select_fields(*args, **kwargs))
        field_answer = encoded(actual)
        ids = [{'entity_id': str(n), 'kind': rng.choice(['company', 'person']),
                'published_at': '2026-01-01T00:00:00Z'} for n in range(4)]
        events = [decision('merge', actor='operator', reason='reviewed', at=f'2026-02-0{n+1}T00:00:00Z',
                           left=str(rng.randrange(4)), right=str(rng.randrange(4)),
                           depends_on=[]) for n in range(3)]
        if index % 2:
            events.append(decision('reverse', actor='operator', reason='corrected',
                                   at='2026-03-01T00:00:00Z', target=events[0]['decision_id']))
        actual = outcome(lambda: asdict(identity.replay(ids, events, AS_OF)))
        yield {"fields": field_answer, "identity": encoded(actual)}


@pytest.mark.parametrize("actual,expected", zip(answers(len(HELD["cases"])), HELD["cases"]))
def test_configured_merge_explicit_answers(actual, expected):
    assert actual == expected
