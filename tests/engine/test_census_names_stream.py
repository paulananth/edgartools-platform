"""Full-stream configured names against the independent retired extraction oracle."""
from collections import defaultdict
import io
import json
from pathlib import Path

import pytest
from edgar_warehouse.rules import files

from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers import source_stream
from tests.mdm.test_clean_name_census import gleif
from tests.support import retired_name_census as oracle

RULE = Path(__file__).resolve().parents[2] / 'rules/sources/gleif/census-names-stream.yaml'


@pytest.fixture(autouse=True)
def no_custom_steps(monkeypatch):
    monkeypatch.setattr('edgar_warehouse.rules.source_engine.STEPS', {})


def project(records, wanted):
    found = []
    engine = source_stream._policy(files.load(RULE))[1]
    receipt = engine.stream_json_array(
        io.BytesIO(json.dumps({'records': records}).encode()), wrapper='records',
        lookups={'wanted': wanted}, context={'publication_count':len(records)}, max_bytes=1048576, max_record=1048576,
        max_records=100000, on_reading=lambda reading, ordinal: found.append(reading.tables))
    assert receipt['record_count'] == len(records)
    return found


def expected(row, wanted):
    entity = row.get('Entity') or {}
    tables = {'a_legal': [], 'b_other': [], 'c_transliterated': []}
    if oracle._text(entity.get('EntityCategory')) == 'BRANCH':
        return tables
    lei = oracle._text(row.get('LEI'))
    if not lei:
        return tables
    key = oracle.legal_form_key(oracle._text(entity.get('LegalName')))
    if key in wanted:
        last = oracle._text((row.get('Registration') or {}).get('LastUpdateDate'))
        tables['a_legal'].append({'key': key, 'lei': lei, 'updated': last})
    for container, item, table in [('OtherEntityNames','OtherEntityName','b_other'),
                                  ('TransliteratedOtherEntityNames','TransliteratedOtherEntityName','c_transliterated')]:
        names = (entity.get(container) or {}).get(item) or []
        for name in names if isinstance(names, list) else [names]:
            text = oracle._text(name)
            key = oracle.legal_form_key(text)
            if text and key in wanted:
                tables[table].append({'key': key, 'lei': lei})
    return tables


@pytest.mark.parametrize('value', [None, '', ' ', False, 0, 7, [], {}, {'$': None},
                                   {'$': False}, {'$': 7}, {'$':'Électricité Company'},
                                   '\u001cApple Incorporated\u001f'])
def test_typed_names_and_identity_match_oracle(value):
    wanted = {'APPLE INC', 'ELECTRICITE CO'}
    records = []
    for field in ['LEI', 'LegalName', 'EntityCategory', 'LastUpdateDate']:
        row = gleif('LEI', 'Apple Inc.', other=['Apple Inc.'])
        target = row if field == 'LEI' else row['Registration'] if field == 'LastUpdateDate' else row['Entity']
        target[field] = value
        row['Entity']['TransliteratedOtherEntityNames'] = {'TransliteratedOtherEntityName': [value]}
        records.append(row)
    assert project(records, wanted) == [expected(row, wanted) for row in records]


@pytest.mark.parametrize('category,lei', [('BRANCH','LEI'), ('GENERAL',None)])
@pytest.mark.parametrize('bad', ['bad', [1], 12])
def test_ineligible_identity_skips_other_containers_without_sentinel_paths(category, lei, bad):
    row = gleif(lei, 'Apple Inc.', category=category)
    row['Entity']['OtherEntityNames'] = bad
    row['__no_census_rows__'] = [{'key':'APPLE INC'}]
    assert project([row], {'APPLE INC'}) == [expected(row, {'APPLE INC'})]


def test_unwanted_legal_name_skips_bad_timestamp_but_keeps_wanted_other_names():
    row = gleif('LEI', 'Other LLC', other=['Apple Inc.'])
    row['Registration'] = 'unread'
    assert project([row], {'APPLE INC'}) == [expected(row, {'APPLE INC'})]


def test_timestamp_refusal_precedes_malformed_other_name_container():
    row = gleif('LEI','Apple Inc.')
    row['Registration'] = 'bad'
    row['Entity']['OtherEntityNames'] = 'also bad'
    with pytest.raises(AttributeError):
        expected(row, {'APPLE INC'})
    with pytest.raises(SourceRejected, match='value_type'):
        project([row], {'APPLE INC'})
    row['Registration'] = {}
    with pytest.raises(SourceRejected, match='objects_shape'):
        project([row], {'APPLE INC'})


def test_complete_source_reduction_preserves_duplicates_last_timestamp_and_legal_subtraction():
    wanted = {'APPLE INC', 'WAYFAIR INC'}
    records = [gleif('A','Apple Inc.',other=['Apple Inc.','Wayfair Inc.']),
               gleif('B','Other LLC',other=['Apple Inc.','Apple Inc.']),
               gleif('A','Apple Inc.',updated='later')]
    found = project(records, wanted)
    assert found == [expected(row, wanted) for row in records]
    legal, other = defaultdict(dict), defaultdict(set)
    for tables in found:
        for row in tables['a_legal']:
            legal[row['key']][row['lei']] = row['updated'] or ''
        for name in ['b_other','c_transliterated']:
            for row in tables[name]:
                other[row['key']].add(row['lei'])
    assert legal['APPLE INC'] == {'A':'later'}
    assert other['APPLE INC'] - set(legal['APPLE INC']) == {'B'}
    assert other['WAYFAIR INC'] == {'A'}


def test_deliberate_membership_fault_is_detected_by_independent_expected_rows():
    row = gleif('LEI','Apple Inc.')
    assert project([row], {'WRONG KEY'}) != [expected(row, {'APPLE INC'})]
