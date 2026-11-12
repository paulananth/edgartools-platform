"""GLEIF field projection.

The answer for each case is in `mapper_outcomes.json` (`EXPECTED`)."""
import copy
import json
from pathlib import Path

import pytest
from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm import adapters
from edgar_warehouse.rules import files, source_engine


EXPECTED=json.loads(Path(__file__).with_name('mapper_outcomes.json').read_text())


def contract(member):
    return copy.deepcopy(files.source('gleif')['dataset_contracts'][f'gleif.{member}.v1']['contract'])


def expected(key, outcome):
    """The answer recorded for this case."""
    assert key in EXPECTED, key
    assert json.loads(json.dumps(outcome))==EXPECTED[key]


def project(member, row):
    config=files.load(files.ROOT/'sources/gleif'/f'{member.replace("_","-")}-fields.yaml')
    # The field projection alone; the contract's record checks have their own tests.
    mapped=config['read']['tables']['mapped']
    mapped.pop('checks',None)
    mapped['columns']={k:v for k,v in mapped['columns'].items() if not k.startswith('_')}
    engine=source_engine.SourceEngine(config)
    result=engine.read(json.dumps(row,ensure_ascii=False,allow_nan=False).encode())
    assert not result.deferred
    assert len(result.tables['mapped'])==1
    return result.tables['mapped'][0]


def raw():
    return {'LEI':{'$':'HWUPKR0MPOU8FGXBT394'},'Entity':{
        'EntityCategory':{'$':'GENERAL'},'LegalName':{'$':' Example '},
        'LegalAddress':{'FirstAddressLine':{'$':' \x1cMain\x1f '},
            'AdditionalAddressLine':[{'$':' Suite '},{'$':'\x1c'},{'$':'Wing'}],
            'City':{'$':' City '},'Country':{'$':'US'}},
        'HeadquartersAddress':{'FirstAddressLine':{'$':' Headquarters '},
            'AdditionalAddressLine':[{'$':'1'},{'$':'2'}],
            'Country':{'$':'US'},'PostalCode':{'$':'123'}},'LegalJurisdiction':{'$':'US-DE'}},
        'Registration':{'RegistrationStatus':{'$':'ISSUED'}}}


@pytest.mark.parametrize('case',['complete','blank','missing','empty_address','null_lines','empty_lines'])
def test_level1_projection_matches_exact_values_and_python_whitespace(case):
    row=raw()
    if case=='blank': row['Entity']['LegalName']={'$':'\x1c\x1f '}
    elif case=='missing': row={'LEI':row['LEI'],'Entity':{'EntityCategory':{'$':'GENERAL'}}}
    elif case=='empty_address': row['Entity']['LegalAddress']={'FirstAddressLine':{'$':' '},'AdditionalAddressLine':[{'$':' '}]}
    elif case=='null_lines': row['Entity']['LegalAddress']['AdditionalAddressLine']=None
    elif case=='empty_lines': row['Entity']['LegalAddress']['AdditionalAddressLine']=[]
    expected(f'gleif/level1/{case}',digest(project('level1',row)))


@pytest.mark.parametrize('member',['relationships','reporting_exceptions'])
def test_other_member_fields_and_matching_keep_raw_types(member):
    row={'key':False,'Relationship':{'RelationshipType':{'$':'IS_DIRECTLY_CONSOLIDATED_BY'}}}
    expected(f'gleif/raw/{member}',digest(project(member,row)))


@pytest.mark.parametrize('value',[False,0,{},[{'$':'valid'},{'$':None}],[{'$':False}],[{'$':1}],['text'],[None]])
def test_malformed_address_lines_are_refused(value):
    row=raw();row['Entity']['LegalAddress']['AdditionalAddressLine']=value
    with pytest.raises(adapters.UnsupportedRecord,match='invalid_field_shape'):
        adapters._fields(row,contract('level1')['adapter'])
    with pytest.raises(source_engine.SourceRejected) as failure: project('level1',row)
    assert failure.value.code in ('join_shape','value_type')


@pytest.mark.parametrize('value',[False,0,[],{}])
def test_nontext_field_is_refused(value):
    row=raw();row['Entity']['LegalName']={'$':value}
    with pytest.raises(adapters.UnsupportedRecord,match='invalid_field_shape'):
        adapters._fields(row,contract('level1')['adapter'])
    with pytest.raises(source_engine.SourceRejected) as failure: project('level1',row)
    assert failure.value.code=='value_type'

@pytest.mark.parametrize('value',['plain text', [{'LegalName': {'$': 'hidden'}}], None, False, 0])
def test_scalar_and_repeated_parents_match_dictionary_only_traversal(value):
    row=raw(); row['Entity']=value
    expected(f'gleif/parents/{value!r}',digest(project('level1',row)))

@pytest.mark.parametrize('value',['plain text', [{'$': 'hidden'}]])
def test_reserved_text_alias_is_not_a_literal_dictionary_field(value):
    row=raw(); row['Entity']['LegalName']=value
    expected(f'gleif/alias/{value!r}',digest(project('level1',row)))

@pytest.mark.parametrize('member',['level1','relationships','reporting_exceptions'])
def test_frozen_inline_reading_matches_bundled_recipe(member):
    configured=files.source('gleif')['dataset_contracts'][f'gleif.{member}.v1']['contract']['adapter']['reading']
    recipe=files.load(files.ROOT/'sources/gleif'/f'{member.replace("_","-")}-fields.yaml')
    assert digest(configured)==digest(recipe)

@pytest.mark.parametrize('case',['valid','invalid_lei','non_company','bad_name','bad_address','bad_matching'])
def test_configured_normalization_preserves_assertion_ids_and_deferrals(case):
    row=raw()
    if case=='invalid_lei': row['LEI']['$']='not-an-lei'
    elif case=='non_company': row['Entity']['EntityCategory']['$']='FUND'
    elif case=='bad_name': row['Entity']['LegalName']['$']=False
    elif case=='bad_address': row['Entity']['LegalAddress']['AdditionalAddressLine']=['invalid']
    elif case=='bad_matching': row['Entity']['HeadquartersAddress']['AdditionalAddressLine']=['invalid']
    publication={'artifact_sha256':'a'*64,'member':'level1','publication_key':'fixture',
                 'revision':1,'effective_at':None}
    try:
        assertion=adapters.normalize(row,source_code='gleif.level1.v1',contract=contract('level1'),publication=publication)
        outcome=('assertion',digest(assertion))
    except adapters.UnsupportedRecord as error:
        outcome=('deferred',error.reason,digest(error.detail),error.probable_kind)
    expected(f'gleif/normalize/{case}',outcome)


def test_invalid_reading_configuration_stops_instead_of_deferring_record():
    configured=copy.deepcopy(files.source('gleif')['dataset_contracts']['gleif.level1.v1']['contract'])
    configured['adapter']['reading']['read']['tables']['mapped']['columns']['fields']={'unknown_primitive':{}}
    with pytest.raises(source_engine.SourceRejected): adapters.mapped_values(raw(),configured)


def test_relationship_refusal_precedes_later_matching_shape_failure():
    row=raw()
    row['relationship']={'kind':'UNSUPPORTED'}
    row['Entity']['HeadquartersAddress']['AdditionalAddressLine']=['invalid']
    configured=copy.deepcopy(files.source('gleif')['dataset_contracts']['gleif.level1.v1']['contract'])
    configured['adapter']['relationships']=[{'type_field':'relationship.kind','type_values':{'KNOWN':'owns'}}]
    publication={'artifact_sha256':'a'*64,'member':'level1','publication_key':'fixture','revision':1}
    with pytest.raises(adapters.UnsupportedRecord) as failure:
        adapters.normalize(row,source_code='gleif.level1.v1',contract=configured,publication=publication)
    assert failure.value.reason=='unsupported_relationship_type'


def test_unused_mapping_expressions_are_validated_before_fields_projection():
    configured=copy.deepcopy(files.source('gleif')['dataset_contracts']['gleif.level1.v1']['contract']['adapter'])
    configured['reading']['read']['tables']['mapped']['columns']['matching']={'unknown_primitive':{}}
    with pytest.raises(source_engine.SourceRejected) as failure:
        adapters._fields(raw(),configured)
    assert failure.value.code=='contract'


@pytest.mark.parametrize('part',['adapter','mapping','engine','steps','native','identity','survivorship','evidence'])
def test_mdm_worker_runtime_pins_configured_mapping_dependencies(part,monkeypatch):
    from pathlib import Path
    from edgar_warehouse.workers import mastering_merge,source_mapping
    from edgar_warehouse.workers.__main__ import runtime
    from edgar_warehouse.mdm import identity, survivorship, evidence
    paths={**{m.__name__.rsplit('.',1)[1]:Path(m.__file__) for m in (identity,survivorship,evidence)},
           'adapter':Path(adapters.__file__),'mapping':Path(source_mapping.__file__),
           **dict(zip(('engine','steps','native'),source_engine.runtime_files(),strict=True))}
    selected=paths[part]
    assert selected in mastering_merge.runtime_files()
    before=runtime(mastering_merge)
    original=Path.read_bytes
    def changed(path):
        content=original(path)
        return content+b'\n deliberate dependency fault' if path==selected else content
    monkeypatch.setattr(Path,'read_bytes',changed)
    assert runtime(mastering_merge)!=before
