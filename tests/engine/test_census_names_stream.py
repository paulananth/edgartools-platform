"""Full-stream configured names: the census rows each GLEIF record makes, written independently of the engine."""
from collections import defaultdict
import io
import json
from pathlib import Path

import pytest
from edgar_warehouse.rules import files

from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers.source_traversal import Traversal
from tests.mdm.test_clean_name_census import gleif
from edgar_warehouse.mdm.clean.primitives import NORMALIZERS

RULE = Path(__file__).resolve().parents[2] / 'rules/sources/gleif/census-names-stream.yaml'
legal_form_key = NORMALIZERS['normalize_text@legal-form-kept-v1']


def text(node):
    """A GLEIF value's text (`$` of an element, or the value), stripped; blank or not text is none."""
    value = node.get('$') if isinstance(node, dict) else node
    return value.strip() if isinstance(value, str) and value.strip() else None


@pytest.fixture(autouse=True)
def no_custom_steps(monkeypatch):
    monkeypatch.setattr('edgar_warehouse.rules.source_engine.STEPS', {})


def project(records, wanted):
    found = []
    rules = files.load(RULE)
    rules["read"]["stream"]["container"] = "none"
    receipt = Traversal(rules, archive_policy="configured").scan(
        io.BytesIO(json.dumps({'records': records}).encode()),
        lookups={'wanted': wanted}, context={'publication_count': len(records)},
        on_reading=lambda reading, ordinal: found.append(reading.tables))
    assert receipt['record_count'] == len(records)
    return found


def expected(row, wanted):
    entity = row.get('Entity') or {}
    tables = {'a_legal': [], 'b_other': [], 'c_transliterated': []}
    if text(entity.get('EntityCategory')) == 'BRANCH':
        return tables
    lei = text(row.get('LEI'))
    if not lei:
        return tables
    key = legal_form_key(text(entity.get('LegalName')))
    if key in wanted:
        last = text((row.get('Registration') or {}).get('LastUpdateDate'))
        tables['a_legal'].append({'key': key, 'lei': lei, 'updated': last})
    for container, item, table in [('OtherEntityNames','OtherEntityName','b_other'),
                                  ('TransliteratedOtherEntityNames','TransliteratedOtherEntityName','c_transliterated')]:
        names = (entity.get(container) or {}).get(item) or []
        for name in names if isinstance(names, list) else [names]:
            name_text = text(name)
            key = legal_form_key(name_text)
            if name_text and key in wanted:
                tables[table].append({'key': key, 'lei': lei})
    return tables


@pytest.mark.parametrize('value', [None, '', ' ', False, 0, 7, [], {}, {'$': None},
                                   {'$': False}, {'$': 7}, {'$':'Électricité Company'},
                                   '\u001cApple Incorporated\u001f'])
def test_typed_names_and_identity(value):
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
