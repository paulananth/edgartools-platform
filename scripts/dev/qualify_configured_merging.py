#!/usr/bin/env python3
"""Offline parity/benchmark against the pinned pre-port Python implementation.

Run from the repository: uv run --no-sync python scripts/dev/qualify_configured_merging.py
Uses disposable PostgreSQL 16 with restricted roles. No live source or activation.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import resource
import subprocess
import sys
import time
import types
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
BASELINE = 'e4be301962e0c2c1b6ab6efc0eb500747b7c718e'
AS_OF = '2026-09-18T00:00:00+00:00'


def reference(name):
    """Test-only oracle: exact git snapshot, never a runtime fallback."""
    path = f'edgar_warehouse/mdm/clean/{name}.py'
    source = subprocess.run(['git', 'show', f'{BASELINE}:{path}'], cwd=ROOT,
                            check=True, capture_output=True, text=True).stdout
    qualified = f'edgar_warehouse.mdm.clean._qualification_{name}'
    module = types.ModuleType(qualified)
    sys.modules[qualified] = module
    exec(compile(source, f'{BASELINE}:{path}', 'exec'), module.__dict__)
    return module


def outcome(call):
    try:
        return ('ok', call())
    except (ValueError, KeyError) as error:
        return ('error', type(error).__name__, str(error))


def parity(cases):
    from edgar_warehouse.mdm.clean import identity, survivorship
    from edgar_warehouse.mdm.clean.evidence import assertion, decision
    old_identity, old_fields = reference('identity'), reference('survivorship')
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
        expected = outcome(lambda: old_fields.select_fields(*args, **kwargs))
        actual = outcome(lambda: survivorship.select_fields(*args, **kwargs))
        if actual != expected:
            raise AssertionError(f'Field/profile parity failed at case {index}: {actual!r} != {expected!r}')
        ids = [{'entity_id': str(n), 'kind': rng.choice(['company', 'person']),
                'published_at': '2026-01-01T00:00:00Z'} for n in range(4)]
        events = [decision('merge', actor='operator', reason='reviewed', at=f'2026-02-0{n+1}T00:00:00Z',
                           left=str(rng.randrange(4)), right=str(rng.randrange(4)),
                           depends_on=[]) for n in range(3)]
        if index % 2:
            events.append(decision('reverse', actor='operator', reason='corrected',
                                   at='2026-03-01T00:00:00Z', target=events[0]['decision_id']))
        expected = outcome(lambda: asdict(old_identity.replay(ids, events, AS_OF)))
        actual = outcome(lambda: asdict(identity.replay(ids, events, AS_OF)))
        if actual != expected:
            raise AssertionError(f'Identity parity failed at case {index}: {actual!r} != {expected!r}')
    return {'field_profile_cases': cases, 'identity_cases': cases}


def workload(limit):
    from edgar_warehouse.mdm.clean.evidence import decision
    from tests.integration.test_clean_mdm_postgres import identity_and_binding, source
    rows, identities, decisions = [], [], []
    for n in range(limit):
        row = source(key=str(n), source_code='fixture.primary' if n % 2 == 0 else 'fixture.secondary',
                     fields={'name': f'Company {n}', 'address': {'street': str(n), 'city': '雪'}})
        entity, bind = identity_and_binding(row, str(uuid5(NAMESPACE_URL, f'qualification:{n}')))
        rows.append(row); identities.append(entity); decisions.append(bind)
    for n in range(0, limit-1, 2):
        decisions.append(decision('merge', actor='operator', reason='offline qualification',
                                  at='2026-02-01T00:00:00Z', left=identities[n]['entity_id'],
                                  right=identities[n+1]['entity_id']))
    return rows, identities, decisions


def measure(mode, limit, repeats):
    from edgar_warehouse.mdm.clean import identity, merge, survivorship
    from edgar_warehouse.mdm.clean.store import canonical
    from tests.integration.test_clean_mdm_postgres import (apply, documents, initialize_database, postgres)
    if mode == 'python':
        old_identity, old_fields = reference('identity'), reference('survivorship')
        merge.replay = old_identity.replay
        merge.select_fields = old_fields.select_fields
    else:
        old_identity, old_fields = identity, survivorship
    rows, ids, decisions = workload(limit)
    claims = survivorship.current_claims(rows, AS_OF, set())
    policy = {'fields': {'company': {'name': {'sources': ['fixture.primary', 'fixture.secondary']},
                                  'address': {'sources': ['fixture.primary', 'fixture.secondary']}}}}
    times = []
    for _ in range(repeats):
        started = time.perf_counter()
        state = old_identity.replay(ids, decisions, AS_OF)
        groups = {}
        for subject, entity in state.bindings.items():
            groups.setdefault(state.canonical[entity], []).append(subject)
        for entity, subjects in groups.items():
            old_fields.select_fields('company', subjects, claims, policy, [], as_of=AS_OF,
                                     policy_digest='p', entity_id=entity)
        times.append(time.perf_counter() - started)
    # Real restricted application role, migrations, commits, retry/readback.
    generator = postgres.__wrapped__()
    admin, app = next(generator)
    try:
        from sqlalchemy import text
        commits, retries = [], []
        hashes, first, receipt = None, None, None
        for _ in range(repeats):
            db = initialize_database(admin, app)
            run_id = str(uuid5(NAMESPACE_URL, 'qualification-run'))
            started = time.perf_counter()
            first = apply(db, 1, assertions=rows, identities=ids, decisions=decisions, run_id=run_id)
            commits.append(time.perf_counter() - started)
            started = time.perf_counter()
            repeated = apply(db, 1, assertions=rows, identities=ids, decisions=decisions, run_id=run_id)
            retries.append(time.perf_counter() - started)
            assert not first['duplicate'] and repeated['duplicate']
            assert {k: v for k, v in first.items() if k != 'duplicate'} == {k: v for k, v in repeated.items() if k != 'duplicate'}, 'Retry must return the same committed generation'
            # Entity bodies include losing-identity aliases and profile values.
            observed = {kind: documents(db, kind) for kind in ['entity', 'review', 'relationship']}
            current = {kind: hashlib.sha256(canonical(body).encode()).hexdigest() for kind, body in observed.items()}
            if hashes is not None:
                assert hashes == current, 'Fresh replay changed business projections'
            hashes = current
            with db.application.connect() as conn:
                receipt = dict(conn.execute(text('SELECT request_hash, policy_digest, generation, checkpoint, consumer FROM mdm.batch WHERE batch_id=:b'), {'b': 'work-1'}).mappings().one())
        result = {'mode': mode, 'records': limit, 'pure_seconds': sorted(times)[len(times)//2],
                  'commit_seconds': sorted(commits)[len(commits)//2], 'retry_seconds': sorted(retries)[len(retries)//2],
                  'commit_samples': commits, 'retry_samples': retries,
                  'projection_hashes': hashes, 'result': first, 'receipt': receipt}
    finally:
        try:
            next(generator)
        except StopIteration:
            pass
    result['max_rss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=200)
    parser.add_argument('--cases', type=int, default=250)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--mode', choices=['python', 'native'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not (2 <= args.limit <= 600 and 1 <= args.cases <= 10000 and 1 <= args.repeats <= 10):
        parser.error('limit 2..600, cases 1..10000, repeats 1..10')
    if args.mode:
        result = measure(args.mode, args.limit, args.repeats)
    else:
        from edgar_warehouse.workers import mdm_merge
        from edgar_warehouse.workers.__main__ import runtime
        result = {'baseline': BASELINE, 'native_runtime_digest': runtime(mdm_merge),
                  'parity': parity(args.cases), 'runs': []}
        for mode in ['python', 'native']:
            completed = subprocess.run([sys.executable, __file__, '--mode', mode, '--limit', str(args.limit),
                                        '--repeats', str(args.repeats)], check=False, capture_output=True, text=True)
            if completed.returncode:
                raise SystemExit(completed.stderr)
            result['runs'].append(json.loads(completed.stdout))
        old, new = result['runs']
        assert old['projection_hashes'] == new['projection_hashes'], 'Full-path projection hashes differ'
        assert old['result'] == new['result'], 'Committed generations differ'
        assert old['receipt'] == new['receipt'], 'Commit request/policy receipts differ'
    output = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(output + '\n')
    print(output)


if __name__ == '__main__':
    main()
