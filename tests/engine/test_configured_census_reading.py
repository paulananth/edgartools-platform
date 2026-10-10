"""Census construction from the configured complete reading, compared with its retired
extraction/counting path (`tests/support/retired_name_census.py`)."""
from copy import deepcopy
import hashlib
import io

import pytest

from edgar_warehouse.mdm.clean import name_census
from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.rules import files
from tests.mdm.test_clean_name_census import (
    APPLE, COMPLETE_READING, WAYFAIR, archive, configured, gleif, metadata, TestTheCascade as CascadeFixture,
)
from tests.support import retired_name_census as retained


@pytest.fixture(autouse=True)
def no_custom_steps(monkeypatch):
    monkeypatch.setattr('edgar_warehouse.rules.source_engine.STEPS', {})


def compare(filers, records, *, cascade=None, recipe=None):
    raw = archive(records)
    population = {'capture_run_id':'fixed', 'filers':len(filers)}
    actual = configured(filers, records, cascade=cascade, recipe=recipe, population=population,
                        archive_sha256=hashlib.sha256(raw).hexdigest())
    expected = retained.build(gleif_archive=io.BytesIO(raw), filers=filers, sec_population=population,
                              gleif_metadata=metadata(len(records)), gleif_sha256=hashlib.sha256(raw).hexdigest(),
                              cascade=cascade)
    assert actual == expected
    return actual


@pytest.mark.parametrize('value', [None, '', '  ', False, 0, 7, [], {}, {'$':None}, {'$':7},
                                    {'$':False}, {'$':'\u001cApple Incorporated\u001f'},
                                    'Électricité Company', {'$':'Apple Inc.'}])
def test_typed_legal_name_metadata_and_other_name_shapes_keep_historical_counts(value):
    row = gleif('HWUPKR0MPOU8FGXBT394', 'Apple Inc.')
    row['Entity']['LegalName'] = value
    row['Entity']['OtherEntityNames'] = {'OtherEntityName': [value, {'$':'Apple Inc.'}]}
    row['Entity']['TransliteratedOtherEntityNames'] = {'TransliteratedOtherEntityName': value}
    compare([APPLE, ('2','Électricité Company',['Apple Incorporated'])], [row])


@pytest.mark.parametrize('field', ['LEI', 'EntityCategory', 'LastUpdateDate'])
@pytest.mark.parametrize('value', [None, False, 12, {'$':False}, {'$':12}, {'$':'\u001cX\u001f'}])
def test_non_text_identity_values_and_python_whitespace_keep_historical_output(field, value):
    row = gleif('HWUPKR0MPOU8FGXBT394', 'Apple Inc.')
    target = row if field == 'LEI' else row['Entity'] if field == 'EntityCategory' else row['Registration']
    target[field] = value
    compare([APPLE], [row])


def test_whole_archive_construction_counts_former_names_branches_duplicates_and_caps():
    records = [gleif(f'LEI{i}', 'Apple Inc.', other=['Apple Inc.', 'Wayfair Inc.']) for i in range(8)]
    records += [gleif('LEI0','Apple Inc.',updated='2026-09-02T00:00:00Z'),
                gleif('BRANCH','Apple Inc.',category='BRANCH'),
                gleif('OTHER','THE Other Corporation',other=['Apple Inc.','Apple Inc.'])]
    filers = [APPLE, WAYFAIR] + [(str(i),'Some Other Company',['APPLE INC']) for i in range(8)]
    found = compare(filers, records)
    assert found['entries']['APPLE INC']['cik_count'] == 9
    assert found['entries']['APPLE INC']['lei_count'] == 8
    assert len(found['entries']['APPLE INC']['ciks']) == 5
    assert found['entries']['APPLE INC']['other_name_holders'] == 1
    assert found['entries']['APPLE INC']['leis'][0][1] == '2026-09-02T00:00:00Z'
    assert found['entries']['WAYFAIR INC']['other_name_holders'] == 8


def test_configured_reading_preserves_actual_cascade_assignments():
    from edgar_warehouse.mdm.clean import cascade
    from edgar_warehouse.mdm.clean.company_source import POLICY
    from edgar_warehouse.mdm.clean.gleif_source import dataset_contract
    helper = CascadeFixture()
    filer = cascade.Filer(cik=APPLE[0], key='APPLE INC',
                         place=cascade.place({'street':'1 APPLE PARK WAY','city':'CUPERTINO',
                                              'postcode':'95014','country':'US'}),
                         incorporated='US-CA', business_country='US')
    spec = {'spec':cascade.spec(POLICY), 'filers':[filer], 'gleif_contract':dataset_contract('level1')}  # the oracle maps through the contract
    records = [helper.native('HWUPKR0MPOU8FGXBT394','Apple Inc.','1 Apple Park Way'),
               helper.native('5493001KJTIIGC8Y1R12','Fruit LLC','1 Rue de Paris', country='FR')]
    records[1]['Entity']['OtherEntityNames'] = {'OtherEntityName':{'$':'Apple Inc.'}}
    found = compare([APPLE], records, cascade=spec)
    assert found['cascade']['assignments'][APPLE[0]]['lei'] == 'HWUPKR0MPOU8FGXBT394'


def test_deliberate_recipe_fault_fails_actual_census_counts():
    recipe = deepcopy(files.load(COMPLETE_READING))
    recipe['read']['tables']['a_legal']['columns']['key'] = {'const':{'value':'WRONG KEY'}}
    with pytest.raises(AssertionError):
        compare([APPLE], [gleif('HWUPKR0MPOU8FGXBT394','Apple Inc.')], recipe=recipe)


def test_retired_extractors_are_not_production_symbols_and_limits_fail_closed():
    assert not any(hasattr(name_census, name) for name in
                   ('_text','_other_names','sec_keys','build','cascade_entity','_gleif_other_keys'))
    with pytest.raises(SourceRejected, match='exceeds encoded byte bound'):
        configured([APPLE], [gleif('LEI', 'Apple Inc.', other=['A' * (1024**2)])])


@pytest.mark.parametrize('container', ['OtherEntityNames', 'TransliteratedOtherEntityNames'])
@pytest.mark.parametrize('value', [None, [], {}, False, 0, ''])
def test_empty_other_name_containers_keep_historical_counts(container, value):
    row = gleif('LEI', 'Apple Inc.')
    row['Entity'][container] = value
    compare([APPLE], [row])


@pytest.mark.parametrize('identity', ['branch', 'missing_lei'])
@pytest.mark.parametrize('container', ['OtherEntityNames', 'TransliteratedOtherEntityNames'])
@pytest.mark.parametrize('value', [[{'bad':'shape'}], {'OtherEntityName':['x'] * 100001,
                                                        'TransliteratedOtherEntityName':['x'] * 100001}])
def test_excluded_records_do_not_read_malformed_or_oversized_other_names(identity, container, value):
    row = gleif(None if identity == 'missing_lei' else 'LEI', 'Apple Inc.',
                category='BRANCH' if identity == 'branch' else 'GENERAL')
    row['Entity'][container] = value
    found = compare([APPLE], [row])
    assert found['entries']['APPLE INC']['lei_count'] == 0


@pytest.mark.parametrize('value', [[{'LastUpdateDate':{'$':'not-read'}}], 'malformed'])
def test_unmatched_legal_names_do_not_read_registration(value):
    row = gleif('LEI', 'Unmatched LLC', other=['Apple Inc.'])
    row['Registration'] = value
    found = compare([APPLE], [row])
    assert found['entries']['APPLE INC']['other_name_holders'] == 1


@pytest.mark.parametrize('value', [None, [], {}, False, 0, ''])
def test_empty_registration_and_entity_containers_keep_historical_output(value):
    row = gleif('LEI', 'Apple Inc.')
    row['Registration'] = value
    compare([APPLE], [row])
    row['Entity'] = value
    compare([APPLE], [row])


@pytest.mark.parametrize('category', ['BRANCH', 'FUND'])
def test_cascade_skips_other_names_before_mapping_when_category_is_not_general(category):
    row = gleif('LEI', 'Apple Inc.', category=category)
    row['Entity']['OtherEntityNames'] = {'OtherEntityName':['x'] * 100001}
    assert retained.cascade_entity(row, {}, {'APPLE INC'}) is None
    if category == 'BRANCH':  # never a legal entity: its other names are not read at all
        compare([APPLE], [row])


def test_cascade_missing_lei_does_not_read_truthy_non_object_entity():
    row = {'LEI':None, 'Entity':[{'EntityCategory':'GENERAL'}]}
    assert retained.cascade_entity(row, {}, {'APPLE INC'}) is None


@pytest.mark.parametrize('container', ['Entity', 'Registration', 'OtherEntityNames', 'TransliteratedOtherEntityNames'])
def test_truthy_non_object_containers_still_refuse_eligible_records(container):
    row = gleif('LEI', 'Apple Inc.')
    if container in ('Entity','Registration'):
        row[container] = [{'invalid':'shape'}]
    else:
        row['Entity'][container] = [{'invalid':'shape'}]
    raw = archive([row])
    kwargs = dict(filers=[APPLE], sec_population={'filers':1}, gleif_metadata=metadata(1),
                  gleif_sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(AttributeError):
        retained.build(gleif_archive=io.BytesIO(raw), **kwargs)
    with pytest.raises(SourceRejected):
        configured([APPLE], [row])


def test_census_name_transforms_equal_the_canonical_normalizer_recipes():
    for source, recipe in [('gleif',files.load(COMPLETE_READING)),
                           ('gleif',files.load(files.ROOT / 'sources/gleif/census-names-stream.yaml')),
                           ('sec.submissions.company',name_census.SEC_READING)]:
        canonical = files.load(files.ROOT / f'sources/{source}/name-key.yaml')
        transforms = canonical['read']['tables']['names']['columns']['key']['text']['transforms']
        found = []
        def walk(value):
            if isinstance(value, dict):
                if 'text' in value:
                    found.append(value['text']['transforms'])
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(recipe['read']['tables'])
        assert found and all(steps == transforms for steps in found)


@pytest.mark.parametrize('other', [['malformed'], {'OtherEntityName':['x'] * 100001}])
def test_matched_registration_refusal_precedes_other_name_shape_or_count_refusal(other):
    row = gleif('LEI', 'Apple Inc.')
    row['Registration'] = 'malformed'
    row['Entity']['OtherEntityNames'] = other
    raw = archive([row])
    kwargs = dict(filers=[APPLE], sec_population={'filers':1}, gleif_metadata=metadata(1),
                  gleif_sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(AttributeError, match="'str' object has no attribute 'get'"):
        retained.build(gleif_archive=io.BytesIO(raw), **kwargs)
    with pytest.raises(SourceRejected, match='value_type'):
        configured([APPLE], [row])
