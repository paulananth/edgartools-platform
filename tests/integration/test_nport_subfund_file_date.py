"""Invented N-PORT records through the real reader, adapter and link engine."""
from types import SimpleNamespace

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.adapters import normalize
from edgar_warehouse.mdm.relationships import project, types_of
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers.source_readings import iter_artifacts
from tests.support import source_chain


def normalized(tmp_path, source, table, row):
    store = Artifacts()
    folder = files.ROOT / 'sources' / source
    root = tmp_path / source
    root.mkdir()
    raw = store.put((root / 'input.json').as_uri(), {'tables': {table: [row]}})
    context = store.put((root / 'context.json').as_uri(), {'version': 1, 'input': raw, 'values': {}})
    reading = source_chain.read(store, root / 'read', files.load(folder / 'record.yaml'),
                                [{'input': raw, 'context': context}], 2)
    records = [r['record'] for part, _ in iter_artifacts(reading, store,
               max_bytes=10_000_000, max_rows=100) for r in part['tables'][table]]
    assert len(records) == 1
    code = source + ('.v2' if source == 'sec.nport.registrant' else '.v1')  # the registrant's identifiers moved (ticket 203)
    contract = files.load_source(folder / 'source.yaml')['dataset_contracts'][code]['contract']
    return normalize(records[0], source_code=code, contract=contract,
                     publication={'publication_key': 'invented-delivery', 'revision': 1,
                                  'effective_at': None, 'artifact_sha256': 'a' * 64, 'member': 'invented'})


def fund_row(filed='2026 05 15'):
    return {'series_id': 'S000000001', 'lei': None,
            'latest': {'name': 'Invented Fund', 'cik': '0000000001', 'filed': filed}}


def registrant_row():
    return {'cik': '0000000001', 'latest': {'name': 'Invented Registrant', 'filed': '2026 05 20'},
            'first': {'filed': '2026 04 10'}}


def projected(fund, company, *, resolved=True, target_profile=True):
    bindings = {fund['subject']: 'fund'}
    if resolved:
        bindings[company['subject']] = 'company'
    state = SimpleNamespace(bindings=bindings, canonical={'fund': 'fund', 'company': 'company'})
    claims = {fund['subject']: {'assertion_id': fund['assertion_id'],
              'source_meta': {'effective_at': fund['effective_at']}, 'relationships': fund['relationships']}}
    entities = {'fund': {'kind': 'fund_structure', 'status': 'accepted', 'profiles': fund['profiles']},
                'company': {'kind': 'company', 'status': 'accepted',
                            'profiles': company['profiles'] if target_profile else []}}
    return project(claims, state, entities, '2026-06-30T00:00:00+00:00', types_of(files.policy()))


def test_nport_subfund_uses_filing_observation_and_flags_unknown_inception(tmp_path):
    fund = normalized(tmp_path, 'sec.nport.fund', 'fund', fund_row())
    company = normalized(tmp_path, 'sec.nport.registrant', 'registrant', registrant_row())
    assert fund['effective_at'] == '2026-05-15T00:00:00+00:00'
    assert fund['provenance']['quality']['flags'] == ['subfund_start_is_authoritative']
    assert company['provenance']['quality']['flags'] == ['fund_registration_start_is_authoritative']
    assert company['effective_at'] == '2026-05-20T00:00:00+00:00'
    assert company['profiles'][0]['valid_from'] == '2026-04-10T00:00:00+00:00'
    links, reviews = projected(fund, company)
    assert reviews == []
    assert [(r['type'], r['source_id'], r['target_id']) for r in links] == [('IS_SUBFUND_OF', 'fund', 'company')]
    period = links[0]['periods'][0]
    assert period['valid_from'] == '2026-05-15T00:00:00+00:00'
    assert period['valid_from_basis'] == 'observed'
    # Configured source constants retain lexical scalar text.
    assert period['properties']['source_start_date_is_provisional'] == 'true'


@pytest.mark.parametrize('resolved,target_profile,reason', [
    (False, True, 'unresolved_endpoint'),
    (True, False, 'missing_endpoint_profile'),
])
def test_file_date_does_not_bypass_endpoint_qualification(tmp_path, resolved, target_profile, reason):
    fund = normalized(tmp_path, 'sec.nport.fund', 'fund', fund_row())
    company = normalized(tmp_path, 'sec.nport.registrant', 'registrant', registrant_row())
    links, reviews = projected(fund, company, resolved=resolved, target_profile=target_profile)
    assert links == []
    assert [r['reason'] for r in reviews] == [reason]


@pytest.mark.parametrize('filed,exception,message', [
    (None, SourceRejected, 'missing_provisional_file_date'),
    ('', SourceRejected, 'missing_provisional_file_date'),
    ('bad-date', ValueError, 'Invalid isoformat'),
])
def test_a_missing_or_invalid_filing_date_never_becomes_today(tmp_path, filed, exception, message):
    with pytest.raises(exception, match=message):
        normalized(tmp_path, 'sec.nport.fund', 'fund', fund_row(filed))


@pytest.mark.parametrize('filing', ['latest', 'first'])
@pytest.mark.parametrize('filed,exception,message', [
    (None, SourceRejected, 'missing_provisional_file_date'),
    ('', SourceRejected, 'missing_provisional_file_date'),
    ('bad-date', ValueError, 'Invalid isoformat|Effective time must include a timezone'),
])
def test_registrant_requires_valid_filing_and_registration_observations(tmp_path, filing, filed, exception, message):
    row = registrant_row()
    row[filing]['filed'] = filed
    fund = normalized(tmp_path, 'sec.nport.fund', 'fund', fund_row())
    with pytest.raises(exception, match=message):
        company = normalized(tmp_path, 'sec.nport.registrant', 'registrant', row)
        # The link engine validates the registration interval; normalization
        # validates the source's effective observation separately.
        projected(fund, company)
