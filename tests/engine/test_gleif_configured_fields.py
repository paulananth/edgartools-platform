"""Native field projection must match the retained mapper before cutover."""
import copy
import json
import pytest
from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.rules import files, source_engine


def contract(member):
    body=copy.deepcopy(files.source('gleif')['mdm'][f'gleif.{member}.v1']['contract'])
    body['adapter'].pop('reading',None)
    return body


def project(member, row):
    config=files.load(files.ROOT/'sources/gleif'/f'{member.replace("_","-")}-fields.yaml')
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
    mapping=contract('level1')['adapter']
    expected={'fields':adapters._fields(row,mapping),'matching':adapters._matching_values(row,mapping)}
    assert digest(project('level1',row))==digest(expected)


@pytest.mark.parametrize('member',['relationships','reporting_exceptions'])
def test_other_member_fields_and_matching_keep_raw_types(member):
    row={'key':False,'Relationship':{'RelationshipType':{'$':'IS_DIRECTLY_CONSOLIDATED_BY'}}}
    mapping=contract(member)['adapter']
    expected={'fields':adapters._fields(row,mapping),'matching':adapters._matching_values(row,mapping)}
    assert digest(project(member,row))==digest(expected)


@pytest.mark.parametrize('value',[False,0,{},[{'$':'valid'},{'$':None}],[{'$':False}],[{'$':1}],['text'],[None]])
def test_malformed_address_lines_refuse_like_retained_mapper(value):
    row=raw();row['Entity']['LegalAddress']['AdditionalAddressLine']=value
    with pytest.raises(adapters.UnsupportedRecord,match='invalid_field_shape'):
        adapters._fields(row,contract('level1')['adapter'])
    with pytest.raises(source_engine.SourceRejected) as failure: project('level1',row)
    assert failure.value.code in ('join_shape','value_type')


@pytest.mark.parametrize('value',[False,0,[],{}])
def test_nontext_field_refuses_like_retained_nullable_text_mapping(value):
    row=raw();row['Entity']['LegalName']={'$':value}
    with pytest.raises(adapters.UnsupportedRecord,match='invalid_field_shape'):
        adapters._fields(row,contract('level1')['adapter'])
    with pytest.raises(source_engine.SourceRejected) as failure: project('level1',row)
    assert failure.value.code=='value_type'

@pytest.mark.parametrize('value',['plain text', [{'LegalName': {'$': 'hidden'}}], None, False, 0])
def test_scalar_and_repeated_parents_match_dictionary_only_traversal(value):
    row=raw(); row['Entity']=value
    mapping=contract('level1')['adapter']
    expected={'fields':adapters._fields(row,mapping),'matching':adapters._matching_values(row,mapping)}
    assert digest(project('level1',row))==digest(expected)

@pytest.mark.parametrize('value',['plain text', [{'$': 'hidden'}]])
def test_reserved_text_alias_is_not_a_literal_dictionary_field(value):
    row=raw(); row['Entity']['LegalName']=value
    mapping=contract('level1')['adapter']
    expected={'fields':adapters._fields(row,mapping),'matching':adapters._matching_values(row,mapping)}
    assert digest(project('level1',row))==digest(expected)

@pytest.mark.parametrize('member',['level1','relationships','reporting_exceptions'])
def test_frozen_inline_reading_matches_bundled_recipe(member):
    configured=files.source('gleif')['mdm'][f'gleif.{member}.v1']['contract']['adapter']['reading']
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
    configured=files.source('gleif')['mdm']['gleif.level1.v1']['contract']
    def outcome(body):
        try:
            return ('assertion',digest(adapters.normalize(row,source_code='gleif.level1.v1',contract=body,publication=publication)))
        except adapters.UnsupportedRecord as error:
            return ('deferred',error.reason,digest(error.detail),error.probable_kind)
    assert outcome(configured)==outcome(contract('level1'))


def test_invalid_reading_configuration_stops_instead_of_deferring_record():
    configured=copy.deepcopy(files.source('gleif')['mdm']['gleif.level1.v1']['contract'])
    configured['adapter']['reading']['read']['tables']['mapped']['columns']['fields']={'unknown_primitive':{}}
    with pytest.raises(source_engine.SourceRejected): adapters.mapped_values(raw(),configured)


def test_relationship_refusal_precedes_later_matching_shape_failure():
    row=raw()
    row['relationship']={'kind':'UNSUPPORTED'}
    row['Entity']['HeadquartersAddress']['AdditionalAddressLine']=['invalid']
    configured=copy.deepcopy(files.source('gleif')['mdm']['gleif.level1.v1']['contract'])
    configured['adapter']['relationships']=[{'type_field':'relationship.kind','type_values':{'KNOWN':'owns'}}]
    retained=copy.deepcopy(configured); retained['adapter'].pop('reading')
    publication={'artifact_sha256':'a'*64,'member':'level1','publication_key':'fixture','revision':1}
    for body in [configured,retained]:
        with pytest.raises(adapters.UnsupportedRecord) as failure:
            adapters.normalize(row,source_code='gleif.level1.v1',contract=body,publication=publication)
        assert failure.value.reason=='unsupported_relationship_type'
